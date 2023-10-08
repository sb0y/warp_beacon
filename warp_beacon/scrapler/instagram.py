import os
import json
from typing import Optional, Callable
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
		except PleaseWaitFewMinutes as e:
			logging.warning("Please wait a few minutes error. Trying to relogin...")
			logging.exception(e)
			#os.unlink(INST_SESSION_FILE)
			return self.scrap(url)
		except LoginRequired as e:
			logging.warning("Session error. Trying to relogin...")
			logging.exception(e)
			self.login()
			video_url = _scrap()
			
		return video_url
	
	def download(self, url: str) -> str:
		media_pk = self.scrap(url)
		media_info = self.media_info(media_pk)
		logging.info("Video type is '%d'", media_info.media_type)
		logging.info("video_url is '%s'", media_pk)
		local_path = self.cl.video_download(media_pk, folder='/tmp')
		return str(local_path)
