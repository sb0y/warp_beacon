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

from warp_beacon.scraper.exceptions import NotFound, UnknownError, TimeOut, Unavailable, FileTooBig, extract_exception_message
from warp_beacon.scraper.abstract import ScraperAbstract

import logging

DOWNLOAD_DIR = "/tmp"

class YoutubeMusicScraper(ScraperAbstract):

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
		max_retries = int(os.environ.get("YT_MUSIC_MAX_RETRIES", default=6))
		pause_secs = int(os.environ.get("YT_MUSIC_PAUSE_BEFORE_RETRY", default=3))
		timeout = int(os.environ.get("YT_MUSIC_TIMEOUT", default=60))
		timeout_increment = int(os.environ.get("YT_MUSIC_TIMEOUT_INCREMENT", default=60))
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
				logging.info("Your `YT_MUSIC_MAX_RETRIES` values is %d", max_retries)
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

	def _download(self, url: str, timeout: int = 0) -> list:
		res = []
		yt = YouTube(url)
		stream = yt.streams.get_audio_only()
		if stream:
			logging.info("Announced audio file size: '%d'", stream.filesize)
			if stream.filesize > 5e+7:
				logging.warning("Downloading size reported by YouTube is over than 50 mb!")
				raise FileTooBig("YouTube file is larger than 50 mb")
			logging.info("Operation timeout is '%d'", timeout)
			local_file = stream.download(
				output_path=DOWNLOAD_DIR,
				max_retries=0,
				timeout=timeout,
				skip_existing=False,
				filename_prefix='yt_download_',
				mp3=True
			)
			logging.info("Temp filename: '%s'", local_file)
			res.append({"local_media_path": self.rename_local_file(local_file), "canonical_name": stream.title, "media_type": "audio"})

		return res

	def download(self, url: str) -> list:
		return self._download_hndlr(self._download, url)
