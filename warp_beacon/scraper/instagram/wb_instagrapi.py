import logging
from typing import Callable
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from pathlib import Path
import requests

from instagrapi import Client
from instagrapi.exceptions import VideoNotDownload

from warp_beacon.scraper.utils import ScraperUtils

class WBClient(Client):
	"""
	patched instagrapi
	"""
	def __init__(self) -> None:
		super().__init__()
		self.progress_callback = None
		self.session = requests.Session()
		# may be I should remove '"Sec-Fetch-*", "Upgrade-Insecure-Requests", "DNT"' ?
		self.session.headers.update({
			"User-Agent": ScraperUtils.get_ua(),
			"Accept": (
				"text/html,application/xhtml+xml,application/xml;"
				"q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
			),
			"Accept-Language": "en-US,en;q=0.9",
			"Accept-Encoding": "gzip, deflate, br",
			"Referer": "https://www.instagram.com/",
			"Connection": "keep-alive",
			#"Sec-Fetch-Site": "same-origin",
			#"Sec-Fetch-Mode": "navigate",
			#"Sec-Fetch-User": "?1",
			#"Sec-Fetch-Dest": "document",
			#"Upgrade-Insecure-Requests": "1",
			#"DNT": "1",
		})
		self.essential_params = {"oe", "oh", "_nc_ht", "_nc_cat", "_nc_oc", "_nc_ohc", "_nc_gid"}

	def set_progress_callback(self, callback: Callable[[int | None, int, Path], None]) -> None:
		if not callback or not callable(callback):
			raise TypeError("Progress callback must be callable")
		self.progress_callback = callback

	def adaptive_chunk_size(self, content_length: int) -> int:
		if content_length < 100_000:
			return 2048
		elif content_length < 5_000_000:
			return 8192
		elif content_length < 100_000_000:
			return 32768
		else:
			return 65536

	def sanitize_instagram_url(self, url: str) -> str:
		if "oh=" in url: # signed url, do not touch
				return url
		parsed = urlparse(url)
		query = parse_qs(parsed.query)
		filtered_query = {k: v for k, v in query.items() if k in self.essential_params}
		new_query = urlencode(filtered_query, doseq=True)
		return urlunparse(parsed._replace(query=new_query))

	def video_download_by_url(self, url: str, filename: str = "", folder: Path = "") -> Path:
		url = self.sanitize_instagram_url(url)
		fname = urlparse(url).path.rsplit("/", 1)[1]
		filename = f"{filename}.{fname.rsplit('.', 1)[1]}" if filename else fname
		path = Path(folder or Path.cwd()) / filename

		logging.info("Downloading video from '%s' to '%s'", url, path)

		prepared = self.session.prepare_request(requests.Request("GET", url))
		logging.info("Prepared headers: %s", prepared.headers)
		response = self.session.send(
			prepared,
			stream=True,
			verify=False,
			proxies=self.public.proxies,
			timeout=self.request_timeout
		)
		response.raise_for_status()
		logging.info("Response headers: %s", response.headers)

		content_length = 0
		try:
			content_length = int(response.headers.get("Content-Length", 0))
		except (TypeError, ValueError):
			logging.warning("Content-Length header is missing or invalid.")

		downloaded = 0
		with open(path, "wb") as f:
			for chunk in response.iter_content(chunk_size=self.adaptive_chunk_size(content_length)):
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
		url = self.sanitize_instagram_url(url)
		fname = urlparse(url).path.rsplit("/", 1)[1]
		filename = f"{filename}.{(filename, fname.rsplit('.', 1)[1]) if filename else fname}"
		path = Path(folder) / filename

		logging.info("Downloading photo from '%s' to '%s'", url, path)
		logging.info("[Downloader] Using proxies: %s", self.public.proxies)

		prepared = self.session.prepare_request(requests.Request("GET", url))
		logging.info("Prepared headers: %s", prepared.headers)
		response = self.session.send(
			prepared,
			stream=True,
			verify=False,
			proxies=self.public.proxies,
			timeout=self.request_timeout
		)
		response.raise_for_status()
		logging.info("Response headers: %s", response.headers)

		content_length = 0
		try:
			content_length = int(
				response.headers.get("x-full-image-content-length")
				or response.headers.get("Content-Length")
				or 0
			)
		except (TypeError, ValueError):
			logging.warning("Content-Length header is missing or invalid.")

		downloaded = 0
		with open(path, "wb") as f:
			response.raw.decode_content = True
			for chunk in response.iter_content(chunk_size=self.adaptive_chunk_size(content_length)):
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