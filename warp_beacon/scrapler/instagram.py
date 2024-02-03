import os
import time
import json
from typing import Optional, Callable, Union
import logging

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes

from scrapler.abstract import ScraplerAbstract

INST_SESSION_FILE = "/var/warp_beacon/inst_session.json"

class InstagramScrapler(ScraplerAbstract):
	cl = None

	def __init__(self) -> None:
		super(InstagramScrapler, self).__init__()
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
		if "stories" in url:
			return "stories", self.scrap_story(url)
		else:
			return "media", self.scrap_media(url)

	def scrap_story(self, url: str) -> str:
		story_url = None
		def _scrap() -> int:
			story_id = self.cl.story_pk_from_url(url)
			logging.info("story_id is '%s'", story_id)
			return story_id
		try:
			story_url = _scrap()
		except LoginRequired as e:
			logging.warning("Session error. Trying to relogin...")
			logging.exception(e)
			self.login()
			story_url = _scrap()
			
		return story_url

	def scrap_media(self, url: str) -> str:
		media_url = None
		def _scrap() -> int:
			media_id = self.cl.media_pk_from_url(url)
			logging.info("media_id is '%s'", media_id)
			return media_id
		try:
			media_url = _scrap()
		except LoginRequired as e:
			logging.warning("Session error. Trying to relogin...")
			logging.exception(e)
			self.login()
			media_url = _scrap()
			
		return media_url
	
	def download_video(self, url: str, media_info: dict) -> dict:
		path = str(self.cl.video_download_by_url(url, folder='/tmp'))
		return {"local_media_path": path, "media_type": "video", "media_info": {"duration": media_info.video_duration}}

	def download_photo(self, url: str) -> dict:
		path = str(self.cl.photo_download_by_url(url, folder='/tmp'))
		return {"local_media_path": path, "media_type": "image"}
	
	def download_story(self, story_info: dict) -> dict:
		path, media_type, media_info = "", "", {}
		if story_info.media_type == 1: # photo
			path = str(self.cl.story_download_by_url(url=story_info.thumbnail_url, folder='/tmp'))
			media_type = "image"
		elif story_info.media_type == 2: # video
			path = str(self.cl.story_download_by_url(url=story_info.video_url, folder='/tmp'))
			media_type = "video"
			media_info["duration"] = story_info.video_duration

		return {"local_media_path": path, "media_type": media_type, "media_info": media_info}

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
				scrap_type, media_pk = self.scrap(url)
				if scrap_type == "media":
					media_info = self.cl.media_info(media_pk)
					logging.info("media_type is '%d', product_type is '%s'", media_info.media_type, media_info.product_type)
					if media_info.media_type == 2 and media_info.product_type == "clips": # Reels
						res.append(self.download_video(url=media_info.video_url, media_info=media_info))
					elif media_info.media_type == 1: # Photo
						res.append(self.download_photo(url=media_info.thumbnail_url))
					elif media_info.media_type == 8: # Album
						res.append(self.download_album(media_info=media_info))
				elif scrap_type == "stories":
					story_info = self.cl.story_info(media_pk)
					logging.info("media_type for story is '%d'", story_info.media_type)
					res.append(self.download_story(story_info=story_info))
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
