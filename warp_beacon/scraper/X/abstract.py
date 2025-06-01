import http.client
import io
import logging
import os
import socket
import ssl
import time
import urllib
from typing import Callable, Optional, Union

import playwright
import playwright.sync_api
import requests
import urllib3
#from pytubefix.exceptions import VideoUnavailable, VideoPrivate, MaxRetriesExceeded
import yt_dlp

from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.scraper.abstract import ScraperAbstract
from warp_beacon.scraper.exceptions import (BadProxy, TimeOut, Unavailable,
                                            extract_exception_message)
from warp_beacon.telegram.types import ReportType


class XAbstract(ScraperAbstract):
	DOWNLOAD_DIR = "/tmp"
	X_MAX_RETRIES_DEFAULT = 2
	X_PAUSE_BEFORE_RETRY_DEFAULT = 3
	X_TIMEOUT_DEFAULT = 15
	X_TIMEOUT_INCREMENT_DEFAULT = 20

	def __init__(self, account: tuple, proxy: dict=None) -> None:
		super().__init__(account, proxy)
		self._download_progress_threshold = 0
	
	def validate_session(self) -> int:
		return 0

	def download_hndlr(self, func: Callable, *args: tuple[Union[str, int, dict, tuple, bool]], **kwargs: dict[Union[str, int, dict, tuple, bool]]) -> Optional[Union[list, dict, str, io.BytesIO]]:
		ret_val = None
		max_retries = int(os.environ.get("X_MAX_RETRIES", default=self.X_MAX_RETRIES_DEFAULT))
		pause_secs = int(os.environ.get("X_PAUSE_BEFORE_RETRY", default=self.X_PAUSE_BEFORE_RETRY_DEFAULT))
		timeout = int(os.environ.get("X_TIMEOUT", default=self.X_TIMEOUT_DEFAULT))
		timeout_increment = int(os.environ.get("X_TIMEOUT_INCREMENT", default=self.X_TIMEOUT_INCREMENT_DEFAULT))
		retries = 0
		while max_retries >= retries:
			try:
				kwargs["timeout"] = timeout
				ret_val = func(*args, **kwargs)
				break
			except urllib3.exceptions.ProxyError as e:
				logging.warning("Proxy error!")
				raise BadProxy(extract_exception_message(e.original_error))
			except (socket.timeout,
					ssl.SSLError,
					http.client.IncompleteRead,
					http.client.HTTPException,
					requests.RequestException,
					urllib.error.URLError,
					urllib.error.HTTPError,
					playwright.sync_api.TimeoutError) as e:
				if hasattr(e, "code") and (int(e.code) == 403 or int(e.code) == 400):
					raise Unavailable(extract_exception_message(e))
				if hasattr(e, "reason") and "Remote end closed connection without response" in str(e.reason):
					raise Unavailable(extract_exception_message(e))
				logging.warning("X read timeout! Retrying in '%d' seconds ...", pause_secs)
				logging.info("Your `X_MAX_RETRIES` values is '%d'", max_retries)
				logging.exception(extract_exception_message(e))
				if max_retries <= retries:
					#self.remove_tmp_files()
					raise TimeOut(extract_exception_message(e))
				retries += 1
				timeout += timeout_increment
				time.sleep(pause_secs)
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

	def download_progress(self, total: int | None, bytes_transferred: int, path: str) -> None:
		if not total:
			return
		percentage_of_completion = round(bytes_transferred / (total or 1) * 100)
		if percentage_of_completion >= self._download_progress_threshold:
			logging.debug("[Download] X file '%s', %d", path, percentage_of_completion)
			msg = {
				"action": "report_download_status",
				"current": bytes_transferred,
				"total": total or 0,
				"message_id": self.job.placeholder_message_id,
				"chat_id": self.job.chat_id,
				"completed": percentage_of_completion >= 100,
				"report_type": ReportType.PROGRESS
			}
			self.status_pipe.send(msg)
			self._download_progress_threshold += 20

	def dlp_on_progress(self, params: dict) -> None:
		if params.get("status", "") == "downloading":
			total_size = int(params.get("total_bytes") or params.get("total_bytes_estimate") or 0)
			if not total_size or total_size < 0:
				logging.warning("[Download worker][yt_dlp]: total_size is '%d'", total_size)
				return
			bytes_downloaded = int(params.get("downloaded_bytes", 0))
			percentage_of_completion = bytes_downloaded / (total_size or 1) * 100
			if total_size == 0 or percentage_of_completion >= self._download_progress_threshold:
				msg = {
					"action": "report_download_status",
					"current": bytes_downloaded,
					"total": total_size,
					"message_id": self.job.placeholder_message_id,
					"chat_id": self.job.chat_id,
					"completed": percentage_of_completion >= 100,
					"report_type": ReportType.PROGRESS
				}
				self.status_pipe.send(msg)
				logging.debug("[Download worker][yt_dlp] Downloaded %d%%", percentage_of_completion)
				if total_size > 0:
					self._download_progress_threshold += 20

	def _download(self, url: str, timeout: int = 60) -> list:
		raise NotImplementedError("You should to implement _download method")

	def download(self, job: DownloadJob) -> list:
		self.job = job
		ret = self.download_hndlr(self._download, job.url)
		return ret