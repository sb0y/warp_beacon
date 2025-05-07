import os
import time
import socket
import ssl
import re
from pathlib import Path
import random
from typing import Callable, Optional, Union

import logging

import email
import imaplib
import json
import requests
import urllib3
from urllib.parse import urljoin, urlparse

from instagrapi import exceptions
from instagrapi.exceptions import UnknownError as IGUnknownError
from instagrapi.mixins.story import Story
from instagrapi.types import Media
from instagrapi.mixins.challenge import ChallengeChoice
#from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes, MediaNotFound, ClientNotFoundError, UserNotFound, ChallengeRequired, \
#	ChallengeSelfieCaptcha, ChallengeUnknownStep, UnknownError as IGUnknownError

from warp_beacon.scraper.exceptions import NotFound, UnknownError, TimeOut, IGRateLimitOccurred, CaptchaIssue, BadProxy, extract_exception_message
from warp_beacon.scraper.abstract import ScraperAbstract
from warp_beacon.jobs.types import JobType
from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.telegram.utils import Utils
from warp_beacon.scraper.instagram.wb_instagrapi import WBClient
from warp_beacon.telegram.types import ReportType

INST_SESSION_FILE_TPL = "/var/warp_beacon/inst_session_account_%d.json"

class InstagramScraper(ScraperAbstract):
	cl = None
	inst_session_file = ""
	timeline_cursor = {}
	client_session_id = ""

	def __init__(self, client_session_id: str, account: tuple, proxy: dict=None) -> None:
		self._download_progress_threshold = 20
		self.client_session_id = client_session_id
		super().__init__(account, proxy)
		#
		self.inst_session_file = INST_SESSION_FILE_TPL % self.account_index
		self.cl = WBClient()
		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			if proxy_dsn:
				self.cl.set_proxy(proxy_dsn)
				logging.info("Using proxy DSN '%s'", proxy_dsn)
		#self.cl.logger.setLevel(logging.DEBUG)
		self.setup_device()
		self.cl.challenge_code_handler = self.challenge_code_handler
		self.cl.change_password_handler = self.change_password_handler
		self.cl.public.headers.update({
			"Connection": "keep-alive",
			"Accept": "*/*",
			"Accept-Encoding": "gzip, deflate, br",
			"Accept-Language": "en-US,en;q=0.9",
			"User-Agent": (
				"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
				"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
			)
		})
		self.cl.set_progress_callback(self.download_progress)

	def setup_device(self) -> None:
		if not self.client_session_id:
			self.client_session_id = self.cl.generate_uuid()
		details = self.account.get("auth_details", {})
		self.cl.delay_range = details.get("delay_range", [1, 3])
		self.cl.set_country_code(details.get("country_code", 1))
		self.cl.set_locale(details.get("locale", "en_US"))
		self.cl.set_timezone_offset(details.get("timezone_offset", 10800))
		self.cl.set_user_agent(details.get("user_agent", "Barcelona 291.0.0.31.111 Android (33/13; 600dpi; 1440x3044; samsung; SM-G998B; p3s; exynos2100; en_US; 493450264)"))
		device = details.get("device", {})
		self.cl.set_device({
			"app_version": device.get("app_version", "291.0.0.31.111"),
			"android_version": device.get("android_version", 33),
			"android_release": device.get("android_release", "13.0.0"),
			"dpi": device.get("dpi", "600dpi"),
			"resolution": device.get("resolution", "1440x3044"),
			"manufacturer": device.get("manufacturer", "Samsung"),
			"device": device.get("device", "p3s"),
			"model": device.get("model", "SM-G998B"),
			"cpu": device.get("cpu", "exynos2100"),
			"version_code": device.get("version_code", "493450264")
		})
		uuids = device.get("uuids", {})
		self.cl.set_uuids({
			"phone_id": uuids.get("phone_id", self.cl.generate_uuid()),
			"uuid": uuids.get("uuid", self.cl.generate_uuid()),
			"client_session_id": self.client_session_id,
			"advertising_id": uuids.get("advertising_id", self.cl.generate_uuid()),
			"device_id": uuids.get("device_id", self.cl.generate_uuid())
		})

	def safe_write_session(self) -> None:
		cl_settings = self.cl.get_settings()
		cl_settings["warp_timeline_cursor"] = self.timeline_cursor
		tmp_fname = f"{self.inst_session_file}~"
		with open(tmp_fname, 'w+', encoding="utf-8") as f:
			f.write(json.dumps(cl_settings))
		if os.path.exists(self.inst_session_file):
			os.unlink(self.inst_session_file)
		os.rename(tmp_fname, self.inst_session_file)

	def load_session(self) -> None:
		if os.path.exists(self.inst_session_file):
			logging.info("Loading existing session file '%s'", self.inst_session_file)
			with open(self.inst_session_file, 'r', encoding="utf-8") as f:
				js = json.loads(f.read())
				if "warp_timeline_cursor" in js:
					self.timeline_cursor = js.get("warp_timeline_cursor", {})
					del js["warp_timeline_cursor"]
				self.cl.set_settings(js)
		else:
			self.download_hndlr(self.login)

	def login(self) -> None:
		username = self.account["login"]
		password = self.account["password"]
		if username and password:
			self.cl.login(username=username, password=password, verification_code="")
		self.safe_write_session()

	def validate_session(self) -> int:
		from warp_beacon.scheduler.instagram_human import InstagramHuman
		self.load_session()
		inst_human = InstagramHuman(self)
		inst_human.simulate_activity()
		self.safe_write_session()
		return inst_human.operations_count
	
	def scroll_content(self, last_pk: int) -> None:
		from warp_beacon.scheduler.instagram_human import InstagramHuman
		self.load_session()
		inst_human = InstagramHuman(self)
		inst_human.scroll_content(last_pk)
		self.safe_write_session()
		return inst_human.operations_count

	def scrap(self, url: str) -> tuple[str]:
		self.load_session()
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
		except exceptions.LoginRequired as e:
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
	
	def download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
		ret_val = {}
		max_retries = int(os.environ.get("IG_MAX_RETRIES", default=5))
		retries = 0
		while max_retries >= retries:
			try:
				ret_val = func(*args, **kwargs)
				break
			except urllib3.exceptions.ProxyError as e:
				logging.warning("Proxy error!")
				raise BadProxy(extract_exception_message(e.original_error))
			except exceptions.ClientConnectionError as e:
				msg = str(e.message)
				if "ProxyError" in msg:
					raise BadProxy(msg)
				logging.warning("Instagram read timeout! Retrying in 2 seconds ...")
				logging.info("Your `IG_MAX_RETRIES` values is %d", max_retries)
				logging.exception(e)
				if max_retries <= retries:
					raise TimeOut(extract_exception_message(e))
				retries += 1
				time.sleep(2)
			except(exceptions.ChallengeRequired, exceptions.ChallengeSelfieCaptcha, exceptions.ChallengeUnknownStep) as e:
				logging.warning("Instagram wants Challange!")
				logging.exception(e)
				raise CaptchaIssue("a captcha issue arose")
			except exceptions.LoginRequired as e:
				logging.error("LoginRequired occurred in download handler!")
				logging.exception(e)
				old_session = self.cl.get_settings()
				self.cl.set_settings({})
				self.setup_device()
				self.cl.set_uuids(old_session["uuids"])
				if os.path.exists(self.inst_session_file):
					os.unlink(self.inst_session_file)
				time.sleep(5)
				self.load_session()
			except AssertionError as e:
				raise IGRateLimitOccurred("IG rate limit occurred")
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

	def download_video(self, url: str, media_info: Media) -> dict:
		self.cl.request_timeout = int(os.environ.get("IG_REQUEST_TIMEOUT", default=60))
		path = self.download_hndlr(self.cl.video_download_by_url, url, folder='/tmp')
		return {
			"local_media_path": self.rename_local_file(str(path)),
			"canonical_name": self.extract_canonical_name(media_info),
			"media_type": JobType.VIDEO,
			"last_pk": media_info.pk,
			"media_info": {"duration": round(media_info.video_duration)}
		}

	def download_photo(self, url: str, media_info: Media) -> dict:
		path = str(self.download_hndlr(self.cl.photo_download_by_url, url, folder='/tmp'))
		path_lowered = path.lower()
		if ".webp" in path_lowered:
			path = InstagramScraper.convert_webp_to_png(path)
		if ".heic" in path_lowered:
			path = InstagramScraper.convert_heic_to_png(path)
		return {
			"local_media_path": self.rename_local_file(path),
			"canonical_name": self.extract_canonical_name(media_info),
			"media_type": JobType.IMAGE,
			"last_pk": media_info.pk
		}

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
			path = str(self.download_hndlr(self.cl.story_download_by_url, url=story_info.thumbnail_url, folder='/tmp'))
			path_lowered = path.lower()
			if ".webp" in path_lowered:
				path = InstagramScraper.convert_webp_to_png(path)
			if ".heic" in path_lowered:
				path = InstagramScraper.convert_heic_to_png(path)
			media_type = JobType.IMAGE
		elif story_info.media_type == 2: # video
			path = str(self.download_hndlr(self.cl.story_download_by_url, url=story_info.video_url, folder='/tmp'))
			media_type = JobType.VIDEO
			media_info["duration"] = story_info.video_duration

		return {"local_media_path": self.rename_local_file(path), "media_type": media_type, "media_info": media_info, "effective_url": effective_url}

	def download_stories(self, stories: list[Story]) -> dict:
		chunks = []
		for stories_chunk in Utils.chunker(stories, 10):
			chunk = []
			for story in stories_chunk:
				chunk.append(self.download_story(story_info=story))
			chunks.append(chunk)

		return {"media_type": JobType.COLLECTION, "save_items": True, "items": chunks}

	def download_album(self, media_info: Media) -> dict:
		chunks = []
		for media_chunk in Utils.chunker(media_info.resources, 10):
			chunk = []
			for media in media_chunk:
				_media_info = self.download_hndlr(self.cl.media_info_v1, media.pk)
				if media.media_type == 1: # photo
					chunk.append(self.download_photo(url=_media_info.thumbnail_url, media_info=_media_info))
				elif media.media_type == 2: # video
					chunk.append(self.download_video(url=_media_info.video_url, media_info=_media_info))
			chunks.append(chunk)

		return {"media_type": JobType.COLLECTION, "items": chunks}

	def extract_canonical_name(self, media: Media) -> str:
		ret = ""
		try:
			if media.title:
				ret = media.title
			if media.caption_text:
				ret += "\n" + media.caption_text
		except Exception as e:
			logging.warning("Failed to extract canonical media name!")
			logging.exception(e)

		return ret

	def download(self, job: DownloadJob) -> Optional[list[dict]]:
		res = []
		self.job = job
		while True:
			try:
				scrap_type, media_id = self.scrap(job.url)
				if scrap_type == "media":
					#self.status_pipe.send({
					#	"action": "report_download_status",
					#	"report_type": ReportType.ANNOUNCE,
					#	"label": "Collecting meta information ...",
					#	"chat_id": self.job.chat_id,
					#	"message_id": self.job.placeholder_message_id
					#})
					media_info = self.download_hndlr(self.cl.media_info_v1, media_id)
					logging.info("media_type is '%d', product_type is '%s'", media_info.media_type, media_info.product_type)
					if media_info.media_type == 2 and media_info.product_type == "clips": # Reels
						res.append(self.download_video(url=media_info.video_url, media_info=media_info))
					elif media_info.media_type == 1: # Photo
						res.append(self.download_photo(url=media_info.thumbnail_url, media_info=media_info))
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
			except exceptions.PleaseWaitFewMinutes as e:
				logging.warning("Please wait a few minutes error.")
				logging.exception(e)
				if os.path.exists(self.inst_session_file):
					os.unlink(self.inst_session_file)
				raise IGRateLimitOccurred("Instagram ratelimit")
			except (exceptions.MediaNotFound, exceptions.ClientNotFoundError, exceptions.UserNotFound) as e:
				raise NotFound(extract_exception_message(e))
			except IGUnknownError as e:
				raise UnknownError(extract_exception_message(e))
		
		self.safe_write_session()
		
		return res
	
	def email_challenge_resolver(self, username: str) -> Optional[str]:
		logging.info("Started email challenge resolver")
		mail = imaplib.IMAP4_SSL(self.account.get("imap_server", "imap.bagrintsev.me"))
		mail.login(self.account.get("imap_login", ""), self.account.get("imap_password", "")) # email server creds
		mail.select("inbox")
		_, data = mail.search(None, "(UNSEEN)")
		ids = data.pop().split()
		for num in reversed(ids):
			mail.store(num, "+FLAGS", "\\Seen")  # mark as read
			_, data = mail.fetch(num, "(RFC822)")
			msg = email.message_from_string(data[0][1].decode())
			payloads = msg.get_payload()
			if not isinstance(payloads, list):
				payloads = [msg]
			code = None
			for payload in payloads:
				body = ''
				try:
					body = payload.get_payload(decode=True).decode()
				except:
					continue
				if "<div" not in body:
					continue
				match = re.search(">([^>]*?({u})[^<]*?)<".format(u=username), body)
				if not match:
					continue
				logging.info("Match from email: '%s'", match.group(1))
				match = re.search(r">(\d{6})<", body)
				if not match:
					logging.info('Skip this email, "code" not found')
					continue
				code = match.group(1)
				if code:
					logging.info("Found IG code at mail server: '%s'", code)
					return code
		return None

	def get_code_from_sms(self, username: str) -> Optional[str]:
		while True:
			code = input(f"Enter code (6 digits) for {username}: ").strip()
			if code and code.isdigit():
				return code
		return None

	def challenge_code_handler(self, username: str, choice: ChallengeChoice) -> bool:
		if choice == ChallengeChoice.SMS:
			return False
			#return self.get_code_from_sms(username)
		elif choice == ChallengeChoice.EMAIL:
			return self.email_challenge_resolver(username)
		
		return False

	def change_password_handler(self, username: str) -> str:
		# Simple way to generate a random string
		chars = list("abcdefghijklmnopqrstuvwxyz1234567890!&£@#")
		password = "".join(random.sample(chars, 10))
		logging.info("Generated new IG password: '%s'", password)
		return password
	
	def download_progress(self, total: int | None, bytes_transferred: int, path: Path) -> None:
		percentage_of_completion = round(bytes_transferred / (total or 1) * 100)
		if percentage_of_completion >= self._download_progress_threshold:
			logging.debug("[Download] IG file '%s', %d", str(path), percentage_of_completion)
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