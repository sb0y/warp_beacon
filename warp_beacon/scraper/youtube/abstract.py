import os
import io
import pathlib
import time
import math
import socket
import ssl
#from abc import abstractmethod
from typing import Callable, Union, Optional
import logging
import json
import urllib
import http.client
import pytubefix.exceptions
import requests
from PIL import Image
import numpy as np
from urllib.parse import urlparse, parse_qs

import pytubefix
from pytubefix import YouTube
from pytubefix.innertube import _default_clients
from pytubefix.streams import Stream
from pytubefix.innertube import InnerTube, _client_id, _client_secret
#from pytubefix.exceptions import VideoUnavailable, VideoPrivate, MaxRetriesExceeded
from pytubefix import request
import yt_dlp

from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.scraper.abstract import ScraperAbstract
#from warp_beacon.mediainfo.abstract import MediaInfoAbstract
from warp_beacon.scraper.exceptions import TimeOut, Unavailable, extract_exception_message

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
	
	def get_video_id(self, url: str) -> Optional[str]:
		parsed_url = urlparse(url)
		query = parse_qs(parsed_url.query)
		return query.get('v', [None])[0]

	def remove_tmp_files(self) -> None:
		for i in os.listdir(self.DOWNLOAD_DIR):
			if "yt_download_" in i:
				os.unlink("%s/%s" % (self.DOWNLOAD_DIR, i))

	def calculate_size_with_padding(self,
		image: Image,
		aspect_ratio_width: int,
		aspect_ratio_height: int,
		target_size: tuple=(320, 320),
		background_color: tuple=(0, 0, 0)
	) -> Image:
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

	def download_hndlr(self, func: Callable, *args: tuple[Union[str, int, dict, tuple, bool]], **kwargs: dict[Union[str, int, dict, tuple, bool]]) -> Optional[Union[list, dict, str, io.BytesIO]]:
		ret_val = None
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
			except pytubefix.exceptions.MaxRetriesExceeded:
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
				if hasattr(e, "code") and (int(e.code) == 403 or int(e.code) == 400):
					raise Unavailable(extract_exception_message(e))
				logging.warning("Youtube read timeout! Retrying in '%d' seconds ...", pause_secs)
				logging.info("Your `YT_MAX_RETRIES` values is '%d'", max_retries)
				logging.exception(extract_exception_message(e))
				if max_retries <= retries:
					self.remove_tmp_files()
					raise TimeOut(extract_exception_message(e))
				retries += 1
				timeout += timeout_increment
				time.sleep(pause_secs)
			except (pytubefix.exceptions.VideoUnavailable, pytubefix.exceptions.VideoPrivate) as e:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.DownloadError as e:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.GeoRestrictedError:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.PostProcessingError as e:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.ExtractorError as e:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.MaxDownloadsReached as e:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.UnavailableVideoError as e:
				raise Unavailable(extract_exception_message(e))
			except yt_dlp.utils.ThrottledDownload as e:
				raise Unavailable(extract_exception_message(e))

		return ret_val

	def yt_on_progress(self, stream: Stream, chunk: bytes, bytes_remaining: int) -> None:
		pass
		#logging.info("bytes: %d, bytes remaining: %d", chunk, bytes_remaining)

	def build_yt(self, url: str, session: bool = True) -> YouTube:
		if session:
			InnerTube.send_message_to_admin_func = self.send_message_to_admin_func
			InnerTube.auth_event = self.auth_event
			InnerTube.wb_account = self.account
			InnerTube.fetch_bearer_token = patched_fetch_bearer_token
		_default_clients["ANDROID"]["innertube_context"]["context"]["client"]["clientVersion"] = "19.08.35"
		_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID"]
		yt_opts = {"url": url, "on_progress_callback": self.yt_on_progress}
		if session:
			yt_opts["client"] = "TV_EMBED"
			yt_opts["use_oauth"] = True
			yt_opts["allow_oauth_cache"] = True
			yt_opts["token_file"] = self.YT_SESSION_FILE % self.account_index
		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			logging.info("Using proxy DSN '%s'", proxy_dsn)
			if proxy_dsn:
				if "https://" in proxy_dsn:
					yt_opts["proxies"] = {"https": proxy_dsn}
				elif "http://" in proxy_dsn:
					yt_opts["proxies"] = {"http": proxy_dsn}
				else:
					logging.warning("Proxy DSN malformed!")
		return YouTube(**yt_opts)
	
	def build_yt_dlp(self, timeout: int = 60) -> yt_dlp.YoutubeDL:
		auth_data = {}
		with open(self.YT_SESSION_FILE % self.account_index, 'r', encoding="utf-8") as f:
			auth_data = json.loads(f.read())
		time_name = str(time.time()).replace('.', '_')
		ydl_opts = {
			'socket_timeout': timeout,
			'outtmpl': f'{self.DOWNLOAD_DIR}/yt_download_{time_name}.%(ext)s',
			'format': 'bestvideo+bestaudio/best',
			'merge_output_format': 'mp4',
			'noplaylist': True,
			'tv_auth': auth_data
		}

		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			logging.info("Using proxy DSN '%s'", proxy_dsn)
			if proxy_dsn:
				ydl_opts["proxy"] = proxy_dsn

		return yt_dlp.YoutubeDL(ydl_opts)
	
	def _download(self, _: str, __: int = 60) -> list:
		raise NotImplementedError("You should to implement _download method")
	
	def _download_yt_dlp(self, _: str, __: int = 60) -> list:
		raise NotImplementedError("You should to implement _download_yt_dlp method")

	def download(self, job: DownloadJob) -> list:
		ret = []
		try:
			ret = self.download_hndlr(self._download, job.url, session=True)
		except (Unavailable, TimeOut):
			logging.warning("Download failed, trying to download with yt_dlp")
		
		try:
			ret = self.download_hndlr(self._download_yt_dlp, job.url)
		except NotImplementedError:
			logging.info("yt_dlp is not supported for this submodule yet")
			raise Unavailable("Сontent unvailable")

		return ret
