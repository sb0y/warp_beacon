import os, io
import pathlib
import time
import socket
import ssl

from abc import abstractmethod
from typing import Callable, Union

import requests
import urllib
import http.client
import requests
from PIL import Image

from warp_beacon.scraper.abstract import ScraperAbstract
from warp_beacon.mediainfo.abstract import MediaInfoAbstract
from warp_beacon.scraper.exceptions import NotFound, UnknownError, TimeOut, Unavailable, extract_exception_message

from pytubefix.exceptions import VideoUnavailable, VideoPrivate, MaxRetriesExceeded

import logging

class YoutubeAbstract(ScraperAbstract):
	DOWNLOAD_DIR = "/tmp"

	def __init__(self) -> None:
		pass

	def __del__(self) -> None:
		pass

	def rename_local_file(self, filename: str) -> str:
		if not os.path.exists(filename):
			raise NameError("No file provided")
		path_info = pathlib.Path(filename)
		ext = path_info.suffix
		old_filename = path_info.stem
		time_name = str(time.time()).replace('.', '_')
		new_filename = "%s%s" % (time_name, ext)
		new_filepath = "%s/%s" % (os.path.dirname(filename), new_filename)

		os.rename(filename, new_filepath)

		return new_filepath

	def remove_tmp_files(self) -> None:
		for i in os.listdir(self.DOWNLOAD_DIR):
			if "yt_download_" in i:
				os.unlink("%s/%s" % (self.DOWNLOAD_DIR, i))

	def download_thumbnail(self, url: str) -> Union[io.BytesIO, None]:
		try:
			reply = requests.get(url, stream=True)
			if reply.ok and reply.status_code == 200:
				image = Image.open(io.BytesIO(reply.content))
				image = MediaInfoAbstract.shrink_image_to_fit(image)
				io_buf = io.BytesIO()
				image.save(io_buf, format='JPEG')
				io_buf.seek(0)
				return io_buf
		except Exception as e:
			logging.error("Failed to download download thumbnail!")
			logging.exception(e)

		return None

	def _download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
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
