import logging
from typing import Callable
from urllib.parse import urlparse
from pathlib import Path
import requests

from instagrapi import Client
from instagrapi.exceptions import VideoNotDownload

class WBClient(Client):
	"""
	patched instagrapi
	"""
	def __init__(self) -> None:
		super().__init__()
		self.progress_callback = None

	def set_progress_callback(self, callback: Callable[[int | None, int, Path], None]) -> None:
		if not callback or not callable(callback):
			raise TypeError("Progress callback must be callable")
		self.progress_callback = callback

	def video_download_by_url(self, url: str, filename: str = "", folder: Path = "") -> Path:
		fname = urlparse(url).path.rsplit("/", 1)[1]
		filename = f"{filename}.{fname.rsplit('.', 1)[1]}" if filename else fname
		path = Path(folder or Path.cwd()) / filename

		logging.info("Downloading video from %s to %s", url, path)

		response = requests.get(url, stream=True, timeout=self.request_timeout)
		response.raise_for_status()

		content_length = 0
		try:
			content_length = int(response.headers.get("Content-Length", 0))
		except (TypeError, ValueError):
			logging.warning("Content-Length header is missing or invalid.")

		downloaded = 0
		with open(path, "wb") as f:
			for chunk in response.iter_content(chunk_size=8192):
				if chunk:
					f.write(chunk)
					downloaded += len(chunk)
					if self.progress_callback:
						try:
							self.progress_callback(
								total=content_length or None,
								bytes_transferred=downloaded,
								path=path
							)
						except Exception as e:
							logging.warning("Progress callback raised an exception!", exc_info=e)


		if content_length and downloaded != content_length:
			raise VideoNotDownload(
				f'Broken file "{path}" (expected {content_length}, got {downloaded})'
			)

		return path.resolve()

	def photo_download_by_url(
		self, url: str, filename: str = "", folder: Path = ""
	) -> Path:
		fname = urlparse(url).path.rsplit("/", 1)[1]
		filename = f"{filename}.{(filename, fname.rsplit('.', 1)[1]) if filename else fname}"
		path = Path(folder) / filename
		response = requests.get(url, stream=True, timeout=self.request_timeout)
		response.raise_for_status()

		content_length = 0
		try:
			content_length = int(response.headers.get("Content-Length", 0))
		except (TypeError, ValueError):
			logging.warning("Content-Length header is missing or invalid.")

		downloaded = 0
		with open(path, "wb") as f:
			response.raw.decode_content = True
			for chunk in response.iter_content(chunk_size=4096):
				if chunk:
					f.write(chunk)
					downloaded += len(chunk)
					if self.progress_callback:
						try:
							self.progress_callback(
								total=content_length or None,
								bytes_transferred=downloaded,
								path=path
							)
						except Exception as e:
							logging.warning("Progress callback raised an exception!", exc_info=e)
		return path.resolve()