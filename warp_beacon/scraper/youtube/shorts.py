import os
import pathlib
import time

import socket
import ssl

from typing import Callable, Union

import requests
import urllib
import http.client

from pytubefix import YouTube
from pytubefix.exceptions import VideoUnavailable, VideoPrivate, MaxRetriesExceeded

from warp_beacon.scraper.exceptions import NotFound, UnknownError, TimeOut, Unavailable, extract_exception_message
from warp_beacon.scraper.abstract import ScraperAbstract

import logging

class YoutubeShortsScraper(ScraperAbstract):
	def __init__(self) -> None:
		pass

	def __del__(self) -> None:
		pass

	def remove_tmp_files(self) -> None:
		for i in os.listdir(DOWNLOAD_DIR):
			if "yt_download_" in i:
				os.unlink("%s/%s" % (DOWNLOAD_DIR, i))

	def _download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
		ret_val = ''
		max_retries = int(os.environ.get("YT_MAX_RETRIES", default=8))
		pause_secs = int(os.environ.get("YT_PAUSE_BEFORE_RETRY", default=3))
		retries = 0
		while max_retries >= retries:
			try:
				ret_val = func(*args, **kwargs)
				break
			except MaxRetriesExceeded:
				# do noting, not interested
				pass
			except (socket.timeout, ssl.SSLError, http.client.HTTPException, requests.RequestException, urllib.error.URLError) as e:
				if hasattr(e, "code") and int(e.code) == 403:
					raise Unavailable(extract_exception_message(e))
				logging.warning("Youtube read timeout! Retrying in %d seconds ...", pause_secs)
				logging.info("Your `YT_MAX_RETRIES` values is %d", max_retries)
				logging.exception(extract_exception_message(e))
				if max_retries <= retries:
					self.remove_tmp_files()
					raise TimeOut(extract_exception_message(e))
				retries += 1
				time.sleep(pause_secs)
			except (VideoUnavailable, VideoPrivate) as e:
				raise Unavailable(extract_exception_message(e))

		return ret_val

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

	def _download(self, url: str) -> list:
		res = []
		timeout = int(os.environ.get("YT_TIMEOUT", default=2))
		yt = YouTube(url)
		stream = yt.streams.get_highest_resolution()
		if stream:
			local_file = stream.download(
				output_path="/tmp",
				max_retries=0,
				timeout=timeout,
				skip_existing=False,
				filename_prefix="yt_download_"
			)
			logging.debug("Temp filename: '%s'", local_file)
			res.append({"local_media_path": self.rename_local_file(local_file), "media_type": "video"})

		return res

	def download(self, url: str) -> list:
		return self._download_hndlr(self._download, url)