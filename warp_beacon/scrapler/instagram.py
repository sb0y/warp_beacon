import os
from pathlib import Path
import time
import json
from typing import Callable, Optional, Union

import requests
import urllib3
import logging

from instagrapi.mixins.story import Story
from instagrapi.types import Media
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes

from warp_beacon.scrapler.abstract import ScraplerAbstract

INST_SESSION_FILE = "/var/warp_beacon/inst_session.json"

class InstagramScrapler(ScraplerAbstract):
	cl = None

	def __init__(self) -> None:
		super().__init__()
		self.cl = Client()

	def safe_write_session(self) -> None:
		tmp_fname = "%s~" % INST_SESSION_FILE
		with open(tmp_fname, 'w+') as f:
			f.write(json.dumps(self.cl.get_settings()))
		if os.path.isfile(INST_SESSION_FILE):
			os.unlink(INST_SESSION_FILE)
		os.rename(tmp_fname, INST_SESSION_FILE)

	def load_session(self) -> None:
		if os.path.exists(INST_SESSION_FILE):
			self.cl.load_settings(INST_SESSION_FILE)
		else:
			self.login()

	def login(self) -> None:
		self.cl = Client()
		username = os.environ.get("INSTAGRAM_LOGIN", default=None)
		password = os.environ.get("INSTAGRAM_PASSWORD", default=None)
		verification_code = os.environ.get("INSTAGRAM_VERIFICATION_CODE", default="")
		if username is not None and password is not None:
			self.cl.login(username=username, password=password, verification_code=verification_code)
		self.safe_write_session()

	def scrap(self, url: str) -> tuple[str]:
		self.load_session()
		def _scrap() -> tuple[str]:
			if "stories" in url:
				url_last_part = list(filter(None, url.split('/')))[-1]
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
	
	def __download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[Path, Media]:
		ret_val = {}
		max_retries = int(os.environ.get("IG_MAX_RETRIES", default=5))
		retries = 0
		while max_retries >= retries:
			try:
				ret_val = func(*args, **kwargs)
				break
			except (requests.exceptions.ConnectionError,
					requests.exceptions.ReadTimeout,
					urllib3.exceptions.ReadTimeoutError,
					urllib3.exceptions.ConnectionError) as e:
				logging.warning("Instagram read timeout! Retrying in 2 seconds ...")
				logging.info("Your `IG_MAX_RETRIES` values is %d", max_retries)
				logging.exception(e)
				if max_retries == retries:
					raise e
				retries += 1
				time.sleep(2)

		return ret_val

	
	def download_video(self, url: str, media_info: dict) -> dict:
		path = self.__download_hndlr(self.cl.video_download_by_url, url, folder='/tmp')
		return {"local_media_path": str(path), "media_type": "video", "media_info": {"duration": media_info.video_duration}}

	def download_photo(self, url: str) -> dict:
		path = self.__download_hndlr(self.cl.photo_download_by_url, url, folder='/tmp')
		return {"local_media_path": str(path), "media_type": "image"}
	
	def download_story(self, story_info: Story) -> dict:
		path, media_type, media_info = "", "", {}
		logging.info("Story id is '%s'", story_info.id)
		effective_story_id = story_info.id
		if '_' in effective_story_id:
			st_parts = effective_story_id.split('_')
			if len(st_parts) > 1:
				effective_story_id = st_parts[0]
		logging.info("Effective story id is '%s'", effective_story_id)
		effective_url = "https://www.instagram.com/stories/%s/%s/" % (story_info.user.username, effective_story_id)
		if story_info.media_type == 1: # photo
			path = self.__download_hndlr(self.cl.story_download_by_url, url=story_info.thumbnail_url, folder='/tmp')
			media_type = "image"
		elif story_info.media_type == 2: # video
			path = self.__download_hndlr(self.cl.story_download_by_url, url=story_info.video_url, folder='/tmp')
			media_type = "video"
			media_info["duration"] = story_info.video_duration

		return {"local_media_path": str(path), "media_type": media_type, "media_info": media_info, "effective_url": effective_url}

	def download_stories(self, stories: list[Story]) -> dict:
		res = []
		for story in stories:
			res.append(self.download_story(story_info=story))

		return {"media_type": "collection", "save_items": True, "items": res}

	def download_album(self, media_info: dict) -> dict:
		res = []
		for i in media_info.resources:
			_media_info = self.cl.media_info(i.pk)
			if i.media_type == 1: # photo
				res.append(self.download_photo(url=_media_info.thumbnail_url))
			elif i.media_type == 2: # video
				res.append(self.download_video(url=_media_info.video_url, media_info=_media_info))

		return {"media_type": "collection", "items": res}

	def download(self, url: str) -> Optional[list[dict]]:
		res = []
		while True:
			try:
				scrap_type, media_id = self.scrap(url)
				if scrap_type == "media":
					media_info = self.__download_hndlr(self.cl.media_info, media_id)
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
						if i["media_type"] == "collection":
							for j in i["items"]:
								if os.path.exists(j["local_media_path"]):
									os.unlink(j["local_media_path"])
						else:
							if os.path.exists(i["local_media_path"]):
								os.unlink(i["local_media_path"])
				os.unlink(INST_SESSION_FILE)
				time.sleep(wait_timeout)
		return res
