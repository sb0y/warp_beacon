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

	def scrap(self, url: str) -> str:
		self.load_session()
		video_url = None
		def _scrap() -> int:
			media_id = self.cl.media_pk_from_url(url)
			logging.info("media_id is '%s'", media_id)
			return int(media_id)
		try:
			video_url = _scrap()
		except LoginRequired as e:
			logging.warning("Session error. Trying to relogin...")
			logging.exception(e)
			self.login()
			video_url = _scrap()
			
		return video_url
	
	def download_video(self, url: str, media_info: dict) -> dict:
		path = str(self.cl.video_download_by_url(url, folder='/tmp'))
		return {"local_media_path": path, "media_type": "video", "media_info": {"duration": media_info.video_duration}}

	def download_photo(self, url: str) -> dict:
		path = str(self.cl.photo_download_by_url(url, folder='/tmp'))
		return {"local_media_path": path, "media_type": "image"}
	
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
				media_pk = self.scrap(url)
				media_info = self.cl.media_info(media_pk)
				logging.info("video_type is '%d'", media_info.media_type)
				logging.info("media_id is '%s'", media_pk)
				if media_info.media_type == 2 and media_info.product_type == "clips": # Reels
					res.append(self.download_video(url=media_info.video_url, media_info=media_info))
				elif media_info.media_type == 1: # Photo
					res.append(self.download_photo(url=media_info.thumbnail_url))
				elif media_info.media_type == 8: # Album
					res.append(self.download_album(media_info=media_info))
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
