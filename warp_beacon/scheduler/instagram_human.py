import time
import random
from datetime import datetime

import logging

from instagrapi.types import UserShort
from warp_beacon.scraper.instagram.instagram import InstagramScraper

class InstagramHuman(object):
	scrapler = None
	default_profiles = ["nasa", "natgeo", "9gag", "spotify", "nba"]

	def __init__(self, scrapler: InstagramScraper) -> None:
		self.scrapler = scrapler

	def simulate_activity(self) -> None:
		now = datetime.now()
		hour = now.hour

		if 6 <= hour < 11:
			self.morning_routine()
		elif 11 <= hour < 18:
			self.daytime_routine()
		elif 18 <= hour < 23:
			self.evening_routine()
		else:
			self.night_routine()

	def morning_routine(self) -> None:
		try:
			logging.info("Starting morning activity simulation")
			self.scrapler.timeline_cursor = self.scrapler.download_hndlr(self.scrapler.cl.get_timeline_feed, "pull_to_refresh", self.scrapler.timeline_cursor.get("next_max_id"))
			time.sleep(random.uniform(3, 7))
			if random.random() > 0.5:
				logging.info("Checking direct ...")
				self.scrapler.download_hndlr(self.scrapler.cl.direct_active_presence)
				time.sleep(random.uniform(2, 5))
			if random.random() > 0.3:
				self.scrapler.download_hndlr(self.scrapler.cl.notification_like_and_comment_on_photo_user_tagged, "everyone")
				self.random_pause()
			if random.random() > 0.5:
				logging.info("Simulation updating reels tray feed ...")
				self.scrapler.download_hndlr(self.scrapler.cl.get_reels_tray_feed, "pull_to_refresh")
				self.random_pause()
			if random.random() > 0.8:
				self.profile_view()
		except Exception as e:
			logging.warning("Error in morning_routine")
			logging.exception(e)

	def daytime_routine(self) -> None:
		try:
			logging.info("Starting day fast check activity simulation")
			self.scrapler.download_hndlr(self.scrapler.cl.get_timeline_feed, "pull_to_refresh")
			time.sleep(random.uniform(2, 5))
			if random.random() > 0.5:
				self.scrapler.download_hndlr(self.scrapler.cl.get_reels_tray_feed, "pull_to_refresh")
				self.random_pause()
		except Exception as e:
			logging.warning("Error in daytime_routine")
			logging.exception(e)

	def evening_routine(self) -> None:
		try:
			logging.info("Starting evening active user simulation")
			self.scrapler.download_hndlr(self.scrapler.cl.get_timeline_feed, "pull_to_refresh")
			time.sleep(random.uniform(2, 5))
			self.scrapler.download_hndlr(self.scrapler.cl.get_reels_tray_feed, "pull_to_refresh")
			time.sleep(random.uniform(2, 5))
			if random.random() > 0.5:
				self.scrapler.download_hndlr(self.scrapler.cl.direct_active_presence)
				time.sleep(random.uniform(2, 5))
			if random.random() > 0.5:
				logging.info("Checking notifications, tags ...")
				self.scrapler.download_hndlr(self.scrapler.cl.notification_like_and_comment_on_photo_user_tagged, "everyone")
				self.random_pause()
			if random.random() > 0.4:
				logging.info("Watching reels ...")
				self.scrapler.download_hndlr(self.scrapler.cl.reels)
				self.random_pause()
			if random.random() > 0.6:
				logging.info("Simulation profile view ...")
				self.profile_view()
				self.random_pause()
		except Exception as e:
			logging.warning("Error in evening_routine")
			logging.exception(e)

	def night_routine(self) -> None:
		try:
			logging.info("Starting night activity simulation")
			if random.random() > 0.7:
				self.scrapler.download_hndlr(self.scrapler.cl.direct_active_presence)
				self.random_pause(short=True)
		except Exception as e:
			logging.warning("Error in night_routine")
			logging.exception(e)

	def random_pause(self, short: bool=False) -> None:
		pause = random.uniform(3, 10) if short else random.uniform(10, 30)
		logging.info("Pause for '%.2f' sec ...", round(pause, 2))
		time.sleep(pause)

	def profile_view(self) -> None:
		try:
			logging.info("profile_view ...")
			my_user_id = self.scrapler.cl.user_id
			logging.info("user_following ...")
			friends = list(self.scrapler.download_hndlr(self.scrapler.cl.user_following, my_user_id, amount=random.randint(5, 50)).values())
			time.sleep(random.uniform(2, 5))
			if not friends:
				friends = self.default_profiles
			
			random_friend = random.choice(friends)
			target_user_id = ""
			if isinstance(random_friend, UserShort):
				target_user_id = random_friend.pk
				logging.info("user_info with target_user_id = '%s' ...", target_user_id)
				#self.scrapler.download_hndlr(self.scrapler.cl.user_info, target_user_id)
				self.scrapler.download_hndlr(self.scrapler.cl.user_info_v1, target_user_id)
				time.sleep(random.uniform(2, 5))
			elif isinstance(random_friend, str):
				target_user_id = self.scrapler.download_hndlr(self.scrapler.cl.user_id_from_username, random_friend)
				logging.info("user_info with target_user_id = '%s' ...", target_user_id)
				#self.scrapler.download_hndlr(self.scrapler.cl.user_info, target_user_id)
				self.scrapler.download_hndlr(self.scrapler.cl.user_info_v1, target_user_id)
				time.sleep(random.uniform(2, 5))
			
			if random.random() > 0.5:
				logging.info("Checking direct ...")
				self.scrapler.download_hndlr(self.scrapler.cl.direct_active_presence)
				self.random_pause()

			if random.random() > 0.3:
				logging.info("Checking notifications, tags ...")
				self.scrapler.download_hndlr(self.scrapler.cl.notification_like_and_comment_on_photo_user_tagged, "everyone")
				self.random_pause()
			
			if random.random() > 0.5:
				logging.info("user_medias with target_user_id = '%s' ...", target_user_id)
				self.scrapler.download_hndlr(self.scrapler.cl.user_medias_v1, target_user_id, amount=random.randint(1, 5))
				self.random_pause()
		except Exception as e:
			logging.warning("Error in profile view")
			logging.exception(e)
