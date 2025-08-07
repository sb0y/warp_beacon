import logging
from typing import Callable, List
from copy import deepcopy
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from pathlib import Path
import time
import requests

from instagrapi import Client
from instagrapi.types import Media, User, Story
from instagrapi.exceptions import (
	ClientError,
	#ClientLoginRequired,
	ClientNotFoundError,
	VideoNotDownload,
	MediaNotFound,
	PrivateError
)

from instagrapi.extractors import (
	extract_location,
	#extract_media_v1,
	extract_user_short,
	extract_usertag,
	extract_resource_v1
)

from warp_beacon.scraper.utils import ScraperUtils

def extract_media_v1(data):
	"""Extract media from Private API"""
	media = deepcopy(data)
	if "video_versions" in media:
		# Select Best Quality by Resolutiuon
		media["video_url"] = sorted(
			media["video_versions"], key=lambda o: o["height"] * o["width"]
		)[-1]["url"]
	if media["media_type"] == 2 and not media.get("product_type"):
		media["product_type"] = "feed"
	if "image_versions2" in media:
		media["thumbnail_url"] = sorted(
			media["image_versions2"]["candidates"],
			key=lambda o: o["height"] * o["width"],
		)[-1]["url"]
	if media["media_type"] == 8:
		# remove thumbnail_url and video_url for albums
		# see resources
		media.pop("thumbnail_url", "")
		media.pop("video_url", "")
	location = media.get("location")
	media["location"] = location and extract_location(location)
	media["user"] = extract_user_short(media.get("user"))
	media["usertags"] = sorted(
		[
			extract_usertag(usertag)
			for usertag in media.get("usertags", {}).get("in", [])
		],
		key=lambda tag: tag.user.pk,
	)
	media["like_count"] = media.get("like_count", 0)
	media["has_liked"] = media.get("has_liked", False)
	#media["sponsor_tags"] = [tag["sponsor"] for tag in media.get("sponsor_tags", [])]
	media["sponsor_tags"] = [tag["sponsor"] for tag in media.get("sponsor_tags") or []]
	media["play_count"] = media.get("play_count", 0)
	media["coauthor_producers"] = media.get("coauthor_producers", [])
	return Media(
		caption_text=(media.get("caption") or {}).get("text", ""),
		resources=[
			extract_resource_v1(edge) for edge in media.get("carousel_media", [])
		],
		**media,
	)

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
	
	def media_info(self, media_pk: str, use_cache: bool = True) -> Media:
		"""
		Get Media Information from PK

		Parameters
		----------
		media_pk: str
			Unique identifier of the media
		use_cache: bool, optional
			Whether or not to use information from cache, default value is True

		Returns
		-------
		Media
			An object of Media type
		"""
		media_pk = self.media_pk(media_pk)
		if not use_cache or media_pk not in self._medias_cache:
			media = self.media_info_v1(media_pk)
			self._medias_cache[media_pk] = media
		return deepcopy(
			self._medias_cache[media_pk]
		)  # return copy of cache (dict changes protection)
	
	def media_info_v1(self, media_pk: str) -> Media:
		"""
		Get Media from PK by Private Mobile API

		Parameters
		----------
		media_pk: str
			Unique identifier of the media

		Returns
		-------
		Media
			An object of Media type
		"""
		try:
			result = self.private_request(f"media/{media_pk}/info/")
		except ClientNotFoundError as e:
			raise MediaNotFound(e, media_pk=media_pk, **self.last_json)
		except ClientError as e:
			if "Media not found" in str(e):
				raise MediaNotFound(e, media_pk=media_pk, **self.last_json)
			raise e
		return extract_media_v1(result["items"].pop())
	
	def user_info_by_username(self, username: str, use_cache: bool = True) -> User:
		"""
		Get user object from username

		Parameters
		----------
		username: str
			User name of an instagram account
		use_cache: bool, optional
			Whether or not to use information from cache, default value is True

		Returns
		-------
		User
			An object of User type
		"""
		username = str(username).lower()
		if not use_cache or username not in self._usernames_cache:
			user = self.user_info_by_username_v1(username)
			self._users_cache[user.pk] = user
			self._usernames_cache[user.username] = user.pk
		return self.user_info(self._usernames_cache[username])
	
	def user_info(self, user_id: str, use_cache: bool = True) -> User:
		"""
		Get user object from user id

		Parameters
		----------
		user_id: str
			User id of an instagram account
		use_cache: bool, optional
			Whether or not to use information from cache, default value is True

		Returns
		-------
		User
			An object of User type
		"""
		user_id = str(user_id)
		if not use_cache or user_id not in self._users_cache:
			user = self.user_info_v1(user_id)
			self._users_cache[user_id] = user
			self._usernames_cache[user.username] = user.pk
		return deepcopy(
			self._users_cache[user_id]
		)  # return copy of cache (dict changes protection)
	
	def user_medias(self, user_id: str, amount: int = 0, sleep: int = 0) -> List[Media]:
		"""
		Get a user's media

		Parameters
		----------
		user_id: str
		amount: int, optional
			Maximum number of media to return, default is 0 (all medias)
		sleep: int, optional
			Timeout between page iterations

		Returns
		-------
		List[Media]
			A list of objects of Media
		"""
		amount = int(amount)
		user_id = int(user_id)
		sleep = int(sleep)
		# User may been private, attempt via Private API
		# (You can check is_private, but there may be other reasons,
		#  it is better to try through a Private API)
		medias = self.user_medias_v1(user_id, amount, sleep)
		return medias
	
	def user_medias_v1(self, user_id: str, amount: int = 0, sleep: int = 0) -> List[Media]:
		"""
		Get a user's media by Private Mobile API

		Parameters
		----------
		user_id: str
		amount: int, optional
			Maximum number of media to return, default is 0 (all medias)

		Returns
		-------
		List[Media]
			A list of objects of Media
		"""
		amount = int(amount)
		user_id = int(user_id)
		medias = []
		next_max_id = ""
		while True:
			try:
				medias_page, next_max_id = self.user_medias_paginated_v1(
					user_id, amount, end_cursor=next_max_id
				)
			except PrivateError as e:
				raise e
			except Exception as e:
				self.logger.exception(e)
				break
			medias.extend(medias_page)
			if not next_max_id:
				break
			if amount and len(medias) >= amount:
				break
			if sleep:
				time.sleep(sleep)
		if amount:
			medias = medias[:amount]
		return medias

	def user_stories(self, user_id: str, amount: int = None) -> List[Story]:
		"""
		Get a user's stories

		Parameters
		----------
		user_id: str
		amount: int, optional
			Maximum number of story to return, default is all

		Returns
		-------
		List[Story]
			A list of objects of STory
		"""
		return self.user_stories_v1(user_id, amount)