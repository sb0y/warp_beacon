import os, io
import pathlib
import time
import math
import socket
import ssl
#from abc import abstractmethod
from typing import Callable, Union, Optional
import json
import urllib
import requests
import http.client
from PIL import Image
import numpy as np

from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.scraper.abstract import ScraperAbstract
#from warp_beacon.mediainfo.abstract import MediaInfoAbstract
from warp_beacon.scraper.exceptions import TimeOut, Unavailable, extract_exception_message

from pytubefix import YouTube
from pytubefix.innertube import _default_clients
from pytubefix.streams import Stream
from pytubefix.innertube import InnerTube, _client_id, _client_secret
from pytubefix.exceptions import VideoUnavailable, VideoPrivate, MaxRetriesExceeded
from pytubefix import request

import logging

def patched_fetch_bearer_token(self) -> None:
	"""Fetch an OAuth token."""
	# Subtracting 30 seconds is arbitrary to avoid potential time discrepencies
	start_time = int(time.time() - 30)
	data = {
		'client_id': _client_id,
		'scope': 'https://www.googleapis.com/auth/youtube'
	}
	response = request._execute_request(
		'https://oauth2.googleapis.com/device/code',
		'POST',
		headers={
			'Content-Type': 'application/json'
		},
		data=data
	)
	response_data = json.loads(response.read())
	verification_url = response_data['verification_url']
	user_code = response_data['user_code']

	logging.warning("Please open %s and input code '%s'", verification_url, user_code)
	self.send_message_to_admin_func(
		f"Please open {verification_url} and input code <code>{user_code}</code>.\n\n"
		"Please select a Google account with verified age.\n"
		"This will allow you to avoid error the <b>AgeRestrictedError</b> when accessing some content.",
		account_admins=self.wb_account.get("account_admins", None),
		yt_auth=True)
	self.auth_event.wait()

	data = {
		'client_id': _client_id,
		'client_secret': _client_secret,
		'device_code': response_data['device_code'],
		'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
	}
	response = request._execute_request(
		'https://oauth2.googleapis.com/token',
		'POST',
		headers={
			'Content-Type': 'application/json'
		},
		data=data
	)
	response_data = json.loads(response.read())

	self.access_token = response_data['access_token']
	self.refresh_token = response_data['refresh_token']
	self.expires = start_time + response_data['expires_in']
	self.cache_tokens()

class YoutubeAbstract(ScraperAbstract):
	DOWNLOAD_DIR = "/tmp"
	YT_SESSION_FILE = '/var/warp_beacon/yt_session_%d.json'

	#def __init__(self, account: tuple, proxy: dict=None) -> None:
	#	super().__init__(account, proxy)

	#def __del__(self) -> None:
	#	pass

	def rename_local_file(self, filename: str) -> str:
		if not os.path.exists(filename):
			raise NameError("No file provided")
		path_info = pathlib.Path(filename)
		ext = path_info.suffix
		#old_filename = path_info.stem
		time_name = str(time.time()).replace('.', '_')
		new_filename = "%s%s" % (time_name, ext)
		new_filepath = "%s/%s" % (os.path.dirname(filename), new_filename)

		os.rename(filename, new_filepath)

		return new_filepath

	def remove_tmp_files(self) -> None:
		for i in os.listdir(self.DOWNLOAD_DIR):
			if "yt_download_" in i:
				os.unlink("%s/%s" % (self.DOWNLOAD_DIR, i))

	def calculate_size_with_padding(self, image: Image, aspect_ratio_width: int, aspect_ratio_height: int, target_size: tuple=(320, 320), background_color: tuple=(0, 0, 0)) -> Image:
		aspect_ratio = aspect_ratio_width / aspect_ratio_height
		target_width, target_height = target_size

		height = target_height
		width = int(height * aspect_ratio)

		if width > target_width:
			width = target_width
			height = int(width / aspect_ratio)

		new_image = Image.new("RGB", target_size, background_color)
		image.thumbnail(target_size, Image.Resampling.LANCZOS)

		#if aspect_ratio_height > 4:
		#	image = image.resize((image.size[0], image.size[1]+new_image.size[1]))
		#	target_height += new_image.size[1] - 5

		paste_position = ((target_width - width) // 2, (target_height - height) // 2)
		new_image.paste(image, paste_position)

		return new_image

	def resize_aspect_ratio(self, image: Image, base_width: int = 320) -> Image:
		wpercent = (base_width / float(image.size[0]))
		hsize = int((float(image.size[1]) * float(wpercent)))
		img = image.resize((base_width, hsize), Image.Resampling.LANCZOS)

		return img

	def aspect_ratio(self, size: tuple) -> tuple:
		gcd = math.gcd(size[0], size[1])
		return size[0] // gcd, size[1] // gcd
	
	def crop_black_edges_pil(self, img: Image, threshold: int = 35) -> Image:
		y_nonzero, x_nonzero, _ = np.nonzero(np.array(img) > threshold)
		return img.crop((np.min(x_nonzero), np.min(y_nonzero), np.max(x_nonzero), np.max(y_nonzero)))

	def crop_center(self, image: Image, width: int, height: int) -> Image:
		img_width, img_height = image.size
		left = (img_width - width) // 2
		top = (img_height - height) // 2
		right = left + width
		bottom = top + height

		return image.crop((left, top, right, bottom))

	def download_thumbnail(self, video_id: str, timeout: int, crop_center: dict = None) -> Optional[io.BytesIO]:
		for i in ("https://img.youtube.com/vi/{VIDEO_ID}/maxresdefault.jpg",
				"https://img.youtube.com/vi/{VIDEO_ID}/hqdefault.jpg",
				"https://img.youtube.com/vi/{VIDEO_ID}/sddefault.jpg"):
			try:
				url = i.format(VIDEO_ID=video_id)
				logging.info("Youtube thumbnail url '%s'", url)
				with requests.get(url, timeout=(timeout, timeout)) as response:
					if response.status_code == 200:
						image = Image.open(io.BytesIO(response.content))
						ratio = self.aspect_ratio(image.size)
						image = self.crop_black_edges_pil(image)
						if crop_center:
							image = self.crop_center(image, width=crop_center["width"], height=crop_center["height"])
						logging.info("thumb ratio: '%s'", ratio)
						new_image = self.resize_aspect_ratio(image)
						logging.info("thumb size: '%s'", new_image.size)
						io_buf = io.BytesIO()
						new_image.save(io_buf, format='JPEG', subsampling=0, quality=95, progressive=True, optimize=False)
						logging.info("thumb size: %d kb", io_buf.getbuffer().nbytes / 1024)
						io_buf.seek(0)
						return io_buf
			except Exception as e:
				logging.error("Failed to download download thumbnail!")
				logging.exception(e)

		return None

	def _download_hndlr(self, func: Callable, *args: tuple[Union[str, int, dict, tuple]], **kwargs: dict[Union[str, int, dict, tuple]]) -> Union[str, dict, io.BytesIO]:
		ret_val = ''
		max_retries = int(os.environ.get("YT_MAX_RETRIES", default=self.YT_MAX_RETRIES_DEFAULT))
		pause_secs = int(os.environ.get("YT_PAUSE_BEFORE_RETRY", default=self.YT_PAUSE_BEFORE_RETRY_DEFAULT))
		timeout = int(os.environ.get("YT_TIMEOUT", default=self.YT_TIMEOUT_DEFAULT))
		timeout_increment = int(os.environ.get("YT_TIMEOUT_INCREMENT", default=self.YT_TIMEOUT_INCREMENT_DEFAULT))
		retries = 0
		while max_retries >= retries:
			try:
				kwargs["timeout"] = timeout
				ret_val = func(*args, **kwargs)
				break
			except MaxRetriesExceeded:
				# do noting, not interested
				pass
			#except http.client.IncompleteRead as e:
			except (socket.timeout,
					ssl.SSLError,
					http.client.IncompleteRead,
					http.client.HTTPException,
					requests.RequestException,
					urllib.error.URLError,
					urllib.error.HTTPError) as e:
				if hasattr(e, "code") and int(e.code) == 403:
					raise Unavailable(extract_exception_message(e))
				logging.warning("Youtube read timeout! Retrying in %d seconds ...", pause_secs)
				logging.info("Your `YT_MAX_RETRIES` values is %d", max_retries)
				logging.exception(extract_exception_message(e))
				if max_retries <= retries:
					self.remove_tmp_files()
					raise TimeOut(extract_exception_message(e))
				retries += 1
				timeout += timeout_increment
				time.sleep(pause_secs)
			except (VideoUnavailable, VideoPrivate) as e:
				raise Unavailable(extract_exception_message(e))

		return ret_val

	def yt_on_progress(self, stream: Stream, chunk: bytes, bytes_remaining: int) -> None:
		pass
		#logging.info("bytes: %d, bytes remaining: %d", chunk, bytes_remaining)

	def build_yt(self, url: str) -> YouTube:
		InnerTube.send_message_to_admin_func = self.send_message_to_admin_func
		InnerTube.auth_event = self.auth_event
		InnerTube.wb_account = self.account
		InnerTube.fetch_bearer_token = patched_fetch_bearer_token
		_default_clients["ANDROID"]["innertube_context"]["context"]["client"]["clientVersion"] = "19.08.35"
		_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID"]
		yt_opts = {"url": url, "on_progress_callback": self.yt_on_progress}
		yt_opts["client"] = "TV_EMBED"
		yt_opts["use_oauth"] = True
		yt_opts["allow_oauth_cache"] = True
		yt_opts["token_file"] = self.YT_SESSION_FILE % self.account_index
		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			if proxy_dsn:
				logging.info("Using proxy DSN '%s'", proxy_dsn)
				yt_opts["proxies"] = {"http": proxy_dsn, "https": proxy_dsn}
		return YouTube(**yt_opts)
	
	def _download(self, url: str) -> list:
		raise NotImplementedError("Implement _download method")

	def download(self, job: DownloadJob) -> list:
		return self._download_hndlr(self._download, job.url)
