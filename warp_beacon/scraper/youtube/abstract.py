import http.client
import io
import json
import logging
import math
import os
import socket
import ssl
import time
import urllib
#from abc import abstractmethod
from typing import Callable, Optional, Union
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytubefix
import pytubefix.exceptions
import requests
import urllib3
#from pytubefix.exceptions import VideoUnavailable, VideoPrivate, MaxRetriesExceeded
import yt_dlp
from PIL import Image
from pytubefix import YouTube
from pytubefix.innertube import _default_clients
from pytubefix.streams import Stream

from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.scraper.abstract import ScraperAbstract
from warp_beacon.scraper.exceptions import (BadProxy, TimeOut, Unavailable,
											extract_exception_message)
from warp_beacon.yt_auth import YtAuth

class YoutubeAbstract(ScraperAbstract):
	DOWNLOAD_DIR = "/tmp"
	YT_SESSION_FILE = '/var/warp_beacon/yt_session_%d.json'

	def __init__(self, account: tuple, proxy: dict=None) -> None:
		super().__init__(account, proxy)
		self._download_progress_threshold = 20

	def validate_session(self) -> int:
		try:
			logging.info("Validating YT session(s) ...")
			session_dir = os.path.dirname(self.YT_SESSION_FILE)
			for f in os.listdir(session_dir):
				if f.startswith("yt_session") and f.endswith(".json"):
					yt_sess_file = f"{session_dir}/{f}"
					if os.path.exists(yt_sess_file):
						account_index = int(f.split('_')[-1].rstrip('.json'))
						logging.info("Validating YT session #%d ...", account_index)
						yt_sess_data, exp = {}, 0
						with open(yt_sess_file, 'r', encoding="utf-8") as f:
							yt_sess_data = json.loads(f.read())
							exp = int(yt_sess_data.get("expires", 0))
						if exp <= time.time() + 60:
							yt_auth = YtAuth(account_index=account_index)
							requests_data = yt_auth.refresh_token(refresh_token=yt_sess_data.get("refresh_token", ""))
							if requests_data:
								yt_sess_data.update(requests_data)
								if yt_auth.safe_write_session(yt_sess_data):
									logging.info("YT session #%d validated", account_index)
		except Exception as e:
			logging.error("Failed to refresh Youtube session!")
			logging.exception(e)

		return 0
	
	def get_video_id(self, url: str) -> Optional[str]:
		parsed_url = urlparse(url)
		query = parse_qs(parsed_url.query)
		return query.get('v', [None])[0]

	def remove_tmp_files(self) -> None:
		for i in os.listdir(self.DOWNLOAD_DIR):
			if "yt_download_" in i:
				os.unlink(f"{self.DOWNLOAD_DIR}/{i}")

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
				proxies = None
				if self.proxy:
					dsn = self.proxy.get("dsn", None)
					if dsn:
						proxies = self.build_proxies(dsn)
				with requests.get(url, timeout=(timeout, timeout), proxies=proxies) as response:
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
			except (KeyError, pytubefix.exceptions.RegexMatchError):
				raise Unavailable("Library failed")
			except urllib3.exceptions.ProxyError as e:
				logging.warning("Proxy error!")
				raise BadProxy(extract_exception_message(e.original_error))
			except (socket.timeout,
					ssl.SSLError,
					http.client.IncompleteRead,
					http.client.HTTPException,
					requests.RequestException,
					urllib.error.URLError,
					urllib.error.HTTPError) as e:
				if hasattr(e, "code") and (int(e.code) == 403 or int(e.code) == 400):
					raise Unavailable(extract_exception_message(e))
				if hasattr(e, "reason") and "Remote end closed connection without response" in str(e.reason):
					raise Unavailable(extract_exception_message(e))
				logging.warning("Youtube read timeout! Retrying in '%d' seconds ...", pause_secs)
				logging.info("Your `YT_MAX_RETRIES` values is '%d'", max_retries)
				logging.exception(extract_exception_message(e))
				if max_retries <= retries:
					#self.remove_tmp_files()
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
		total_size = stream.filesize or stream.filesize_approx
		bytes_downloaded = total_size - bytes_remaining
		percentage_of_completion = bytes_downloaded / (total_size or 1) * 100
		if total_size == 0 or percentage_of_completion >= self._download_progress_threshold:
			msg = {
				"action": "report_download_status",
				"current": bytes_downloaded,
				"total": total_size,
				"message_id": self.job.placeholder_message_id,
				"chat_id": self.job.chat_id,
				"completed": percentage_of_completion >= 100
			}
			self.status_pipe.send(msg)
			logging.debug("[Download worker] Downloaded %d%%", percentage_of_completion)
			if total_size > 0:
				self._download_progress_threshold += 20

	def build_proxies(self, proxy_dsn: str) -> dict:
		if not proxy_dsn:
			logging.warning("Empty DSN!")
			return {}
		proxy = {}
		if proxy_dsn:
			if "https://" in proxy_dsn:
				proxy["https"] = proxy_dsn
			elif "http://" in proxy_dsn:
				proxy["http"] = proxy_dsn
			else:
				logging.warning("Proxy DSN malformed!")

		return proxy

	def build_yt(self, url: str, session: bool = True) -> YouTube:
		_default_clients["ANDROID"]["innertube_context"]["context"]["client"]["clientVersion"] = "19.08.35"
		_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID"]
		yt_opts = {"url": url, "on_progress_callback": self.yt_on_progress}
		if session:
			yt_opts["client"] = "TV_EMBED"
			yt_opts["use_oauth"] = True
			yt_opts["allow_oauth_cache"] = True
			yt_opts["token_file"] = self.YT_SESSION_FILE % self.account_index
			if not os.path.exists(yt_opts["token_file"]):
				logging.warning("YT session '%s' file is not found", yt_opts["token_file"])
				self.request_yt_auth()
				self.auth_event.wait()
				yt_auth = YtAuth(account_index=self.account_index)
				device_code = yt_auth.load_device_code()
				if device_code:
					auth_data = yt_auth.confirm_token(device_code=device_code)
					if auth_data:
						yt_auth.safe_write_session(auth_data)
				else:
					logging.error("Failed to fetch YT auth token!")
		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			logging.info("Using proxy DSN '%s'", proxy_dsn)
			if proxy_dsn:
				yt_opts["proxies"] = self.build_proxies(proxy_dsn)
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
	
	def _download(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		raise NotImplementedError("You should to implement _download method")
	
	def _download_yt_dlp(self, url: str, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		raise NotImplementedError("You should to implement _download_yt_dlp method")

	def download(self, job: DownloadJob) -> list:
		self.job = job
		ret = []
		thumbnail = None
		try:
			video_id = self.get_video_id(job.url)
			# shorts custom thumb
			##vinfo = VideoInfo(local_file)
			#thumbnail = self.download_hndlr(self.download_thumbnail, video_id=yt.video_id, crop_center=vinfo.get_demensions())
			if video_id:
				thumbnail = self.download_hndlr(self.download_thumbnail, video_id)
		except Exception as e:
			logging.error("Failed to download thumb!")
			logging.exception(e)

		try:
			#self.status_pipe.send({"action": "report_download_status", "current": 0, "total": 0,
			#						"message_id": self.job.placeholder_message_id, "chat_id": self.job.chat_id})
			ret = self.download_hndlr(self._download, job.url, session=True, thumbnail=thumbnail)
			return ret
		except (Unavailable, TimeOut, KeyError) as e:
			logging.warning("Download failed, trying to download with yt_dlp")
			logging.exception(e)
		
		try:
			ret = self.download_hndlr(self._download_yt_dlp, job.url, thumbnail=thumbnail)
		except NotImplementedError:
			logging.info("yt_dlp is not supported for this submodule yet")
			raise Unavailable("Сontent unvailable")

		return ret
