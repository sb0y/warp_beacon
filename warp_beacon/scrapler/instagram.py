import os
import logging

from instagrapi import Client
from instagrapi.exceptions import LoginRequired

from scrapler.abstract import ScraplerAbstract

INST_SESSION_FILE = "/var/warp_beacon/inst_session.json"

class InstagramScrapler(ScraplerAbstract):
	cl = Client()

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
		self.cl.dump_settings(INST_SESSION_FILE)

	def scrap(self, url: str) -> str:
		self.load_session()
		video_url = None
		def _scrap() -> str:
			media_id = self.cl.media_pk_from_url(url)
			return self.cl.media_info(media_id).video_url
		try:
			video_url = _scrap()
		except LoginRequired as e:
			logging.warning("Session error. Trying to relogin...")
			logging.exception(e)
			self.login()
			video_url = _scrap()
			
		return video_url
	
	def download(self, url: str) -> str:
		video_url = self.scrap(url)
		local_path = self.cl.video_download_by_url(video_url, folder='/tmp')
		return local_path
