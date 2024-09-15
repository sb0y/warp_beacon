import os
import time
import socket
import ssl
from typing import Callable, Optional, Union

import socket
import requests.packages.urllib3.util.connection as urllib3_cn

import json
import requests
import urllib3
from urllib.parse import urljoin, urlparse

from instagrapi.mixins.story import Story
#from instagrapi.types import Media
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes, MediaNotFound, ClientNotFoundError, UserNotFound, UnknownError as IGUnknownError

from warp_beacon.scraper.exceptions import NotFound, UnknownError, TimeOut, extract_exception_message
from warp_beacon.scraper.abstract import ScraperAbstract
from warp_beacon.jobs.types import JobType
from warp_beacon.telegram.utils import Utils

import logging

INST_SESSION_FILE = "/var/warp_beacon/inst_session.json"

class InstagramScraper(ScraperAbstract):
	cl = None
	original_gai_family = None

	def __init__(self) -> None:
		#self.original_gai_family = urllib3_cn.allowed_gai_family
		super().__init__()
		self.cl = Client()
		self.cl.delay_range = [1, 3]
		self.cl.set_country_code(7)
		self.cl.set_locale("en_US")
		self.cl.set_timezone_offset(10800)
		self.cl.set_user_agent("Barcelona 291.0.0.31.111 Android (33/13; 600dpi; 1440x3044; samsung; SM-G998B; p3s; exynos2100; en_US; 493450264)")
		self.cl.set_device({
			"app_version": "291.0.0.31.111",
			"android_version": 33,
			"android_release": "13.0.0",
			"dpi": "600dpi",
			"resolution": "1440x3044",
			"manufacturer": "Samsung",
			"device": "p3s",
			"model": "SM-G998B",
			"cpu": "exynos2100",
			"version_code": "493450264"
		})

	def force_ipv6(self) -> None:
		def allowed_gai_family():
			"""
			https://github.com/shazow/urllib3/blob/master/urllib3/util/connection.py
			"""
			family = socket.AF_INET
			if urllib3_cn.HAS_IPV6:
				family = socket.AF_INET6 # force ipv6 only if it is available
			return family
		urllib3_cn.allowed_gai_family = allowed_gai_family

	def restore_gai(self) -> None:
		urllib3_cn.allowed_gai_family = self.original_gai_family

	def safe_write_session(self) -> None:
		tmp_fname = "%s~" % INST_SESSION_FILE
		with open(tmp_fname, 'w+') as f:
			f.write(json.dumps(self.cl.get_settings()))
		if os.path.exists(INST_SESSION_FILE):
			os.unlink(INST_SESSION_FILE)
		os.rename(tmp_fname, INST_SESSION_FILE)

	def load_session(self) -> None:
		if os.path.exists(INST_SESSION_FILE):
			self.cl.load_settings(INST_SESSION_FILE)
		else:
			self.login()

	def login(self) -> None:
		username = os.environ.get("INSTAGRAM_LOGIN", default=None)
		password = os.environ.get("INSTAGRAM_PASSWORD", default=None)
		verification_code = os.environ.get("INSTAGRAM_VERIFICATION_CODE", default="")
		if username is not None and password is not None:
			self.cl.login(username=username, password=password, verification_code=verification_code)
		self.safe_write_session()

	def scrap(self, url: str) -> tuple[str]:
		#self.force_ipv6()
		self.load_session()
		try:
			self.cl.get_timeline_feed()
		except LoginRequired as e:
			logging.error("Exception occurred while cheking IG session!")
			logging.exception(e)
			old_session = self.cl.get_settings()
			self.cl.set_settings({})
			self.cl.set_uuids(old_session["uuids"])
			if os.path.exists(INST_SESSION_FILE):
				os.unlink(INST_SESSION_FILE)
			time.sleep(5)
			return self.scrap(url)
		def _scrap() -> tuple[str]:
			if "stories" in url:
				# remove URL options
				_url = urljoin(url, urlparse(url).path)
				url_last_part = list(filter(None, _url.split('/')))[-1]
				logging.debug("url last part: '%s'", url_last_part)
				if url_last_part.isnumeric():
					return "story", self.scrap_story(url)
				else:
					return "stories", url_last_part
			else:
				return "media", self.scrap_media(url)
		try:
			return _scrap()
		except LoginRequired as e:
			logging.warning("Session error. Trying to relogin...")
			logging.exception(e)
			self.login()
			return _scrap()

	def scrap_stories(self, username: str) -> list[Story]:
		user_info = self.cl.user_info_by_username(username)
		logging.info("user_id is '%s'", user_info.pk)
		return self.cl.user_stories(user_id=user_info.pk)

	def scrap_story(self, url: str) -> str:
		story_id = self.cl.story_pk_from_url(url)
		logging.info("story_id is '%s'", story_id)
		return story_id

	def scrap_media(self, url: str) -> str:
		media_id = self.cl.media_pk_from_url(url)
		logging.info("media_id is '%s'", media_id)
		return media_id
	
	def _download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
		ret_val = {}
		max_retries = int(os.environ.get("IG_MAX_RETRIES", default=5))
		retries = 0
		while max_retries >= retries:
			try:
				ret_val = func(*args, **kwargs)
				break
			except (socket.timeout,
					ssl.SSLError,
					requests.exceptions.ConnectionError,
					requests.exceptions.ReadTimeout,
					requests.exceptions.ConnectTimeout,
					requests.exceptions.HTTPError,
					urllib3.exceptions.ReadTimeoutError,
					urllib3.exceptions.ConnectionError) as e:
				logging.warning("Instagram read timeout! Retrying in 2 seconds ...")
				logging.info("Your `IG_MAX_RETRIES` values is %d", max_retries)
				logging.exception(e)
				if max_retries <= retries:
					raise TimeOut(extract_exception_message(e))
				retries += 1
				time.sleep(2)

		return ret_val

	def download_video(self, url: str, media_info: dict) -> dict:
		path = self._download_hndlr(self.cl.video_download_by_url, url, folder='/tmp')
		return {"local_media_path": str(path), "media_type": JobType.VIDEO, "media_info": {"duration": round(media_info.video_duration)}}

	def download_photo(self, url: str) -> dict:
		path = str(self._download_hndlr(self.cl.photo_download_by_url, url, folder='/tmp'))
		path_lowered = path.lower()
		if ".webp" in path_lowered:
			path = InstagramScraper.convert_webp_to_png(path)
		if ".heic" in path_lowered:
			path = InstagramScraper.convert_heic_to_png(path)
		return {"local_media_path": path, "media_type": JobType.IMAGE}
	
	def download_story(self, story_info: Story) -> dict:
		path, media_type, media_info = "", JobType.UNKNOWN, {}
		logging.info("Story id is '%s'", story_info.id)
		effective_story_id = story_info.id
		if '_' in effective_story_id:
			st_parts = effective_story_id.split('_')
			if len(st_parts) > 1:
				effective_story_id = st_parts[0]
		logging.info("Effective story id is '%s'", effective_story_id)
		effective_url = "https://www.instagram.com/stories/%s/%s/" % (story_info.user.username, effective_story_id)
		if story_info.media_type == 1: # photo
			path = str(self._download_hndlr(self.cl.story_download_by_url, url=story_info.thumbnail_url, folder='/tmp'))
			path_lowered = path.lower()
			if ".webp" in path_lowered:
				path = InstagramScraper.convert_webp_to_png(path)
			if ".heic" in path_lowered:
				path = InstagramScraper.convert_heic_to_png(path)
			media_type = JobType.IMAGE
		elif story_info.media_type == 2: # video
			path = str(self._download_hndlr(self.cl.story_download_by_url, url=story_info.video_url, folder='/tmp'))
			media_type = JobType.VIDEO
			media_info["duration"] = story_info.video_duration

		return {"local_media_path": path, "media_type": media_type, "media_info": media_info, "effective_url": effective_url}

	def download_stories(self, stories: list[Story]) -> dict:
		chunks = []
		for stories_chunk in Utils.chunker(stories, 10):
			chunk = []
			for story in stories_chunk:
				chunk.append(self.download_story(story_info=story))
			chunks.append(chunk)

		return {"media_type": JobType.COLLECTION, "save_items": True, "items": chunks}

	def download_album(self, media_info: dict) -> dict:
		chunks = []
		for media_chunk in Utils.chunker(media_info.resources, 10):
			chunk = []
			for media in media_chunk:
				_media_info = self.cl.media_info(media.pk)
				if media.media_type == 1: # photo
					chunk.append(self.download_photo(url=_media_info.thumbnail_url))
				elif media.media_type == 2: # video
					chunk.append(self.download_video(url=_media_info.video_url, media_info=_media_info))
			chunks.append(chunk)

		return {"media_type": JobType.COLLECTION, "items": chunks}

	def download(self, url: str) -> Optional[list[dict]]:
		res = []
		while True:
			try:
				scrap_type, media_id = self.scrap(url)
				if scrap_type == "media":
					media_info = self._download_hndlr(self.cl.media_info, media_id)
					logging.info("media_type is '%d', product_type is '%s'", media_info.media_type, media_info.product_type)
					if media_info.media_type == 2 and media_info.product_type == "clips": # Reels
						res.append(self.download_video(url=media_info.video_url, media_info=media_info))
					elif media_info.media_type == 1: # Photo
						res.append(self.download_photo(url=media_info.thumbnail_url))
					elif media_info.media_type == 8: # Album
						res.append(self.download_album(media_info=media_info))
				elif scrap_type == "story":
					story_info = self.cl.story_info(media_id)
					logging.info("media_type for story is '%d'", story_info.media_type)
					res.append(self.download_story(story_info=story_info))
				elif scrap_type == "stories":
					logging.info("Stories download mode")
					res.append(self.download_stories(self.scrap_stories(media_id)))
				break
			except PleaseWaitFewMinutes as e:
				logging.warning("Please wait a few minutes error. Trying to relogin ...")
				logging.exception(e)
				wait_timeout = int(os.environ.get("IG_WAIT_TIMEOUT", default=5))
				logging.info("Waiting %d seconds according configuration option `IG_WAIT_TIMEOUT`", wait_timeout)
				if res:
					for i in res:
						if i["media_type"] == JobType.COLLECTION:
							for j in i["items"]:
								if os.path.exists(j["local_media_path"]):
									os.unlink(j["local_media_path"])
						else:
							if os.path.exists(i["local_media_path"]):
								os.unlink(i["local_media_path"])
				if os.path.exists(INST_SESSION_FILE):
					os.unlink(INST_SESSION_FILE)
				time.sleep(wait_timeout)
			except (MediaNotFound, ClientNotFoundError, UserNotFound) as e:
				raise NotFound(extract_exception_message(e))
			except IGUnknownError as e:
				raise UnknownError(extract_exception_message(e))
		return res
