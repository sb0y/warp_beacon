import time
import random
from typing import Optional
from datetime import datetime

import logging

from instagrapi.types import UserShort
from warp_beacon.scraper.instagram.instagram import InstagramScraper

class InstagramHuman(object):
	default_profiles = ["nasa", "natgeo", "9gag", "spotify", "nba"]

	def __init__(self, scrapler: InstagramScraper) -> None:
		self.scrapler = scrapler
		self.operations_count = 0

	def browse_timeline(self) -> Optional[dict]:
		feed = None
		items = []
		try:
			reason = random.choice(["cold_start_fetch", "pull_to_refresh"])
			feed = self.scrapler.cl.get_timeline_feed(reason=reason)
			self.operations_count += 1
			items = feed.get("feed_items", [])
		except Exception as e:
			logging.warning("Failed to get timeline feed!", exc_info=e)
			return

		seen = []
		if items:
			for item in items:
				media = item.get("media_or_ad")
				logging.debug("Item content: %s", media)
				if not media:
					continue
				media_id = media.get("id")
				#user_id = media.get("user", {}).get("pk")

				if media_id:
					seen.append(str(media_id))
					if random.random() < 0.8:
						try:
							#self.scrapler.cl.media_like(media_id)
							self.scrapler.cl.media_comments(media_id)
							self.operations_count += 1

							self.random_pause(short=True)
						except Exception as e:
							logging.warning("Failed to see comments to media '%s'", media_id, exc_info=e)
					self.random_pause()
		if seen:
			try:
				self.scrapler.cl.media_seen(seen)
				self.operations_count += 1
			except Exception as e:
				logging.warning("Failed to mark timeline feed as seen", exc_info=e)

		return feed

	def watch_stories(self) -> None:
		logging.info("Simulating stories watch ...")
		stories = None
		try:
			stories = self.scrapler.cl.user_stories_v1(self.scrapler.cl.user_id)
			self.operations_count += 1
		except Exception as e:
			logging.warning("Failed to get user stories!", exc_info=e)

		if not stories:
			return

		seen = []
		explore_user = None
		for m in stories[:random.randint(1, len(stories))]:
			try:
				logging.info("Wathing story with pk '%s'", str(m.id))
				seen.append(str(m.id))
				if random.random() > 0.5:
					explore_user = m.user
					break
				self.random_pause()
			except Exception as e:
				logging.warning("Exception while watching content", exc_info=e)

		if seen:
			try:
				self.scrapler.cl.media_seen(seen)
				self.operations_count += 1
				logging.info("Marked '%d' stories as seen", len(seen))
			except Exception as e:
				logging.warning("Failed to mark seen watched watch stories!", exc_info=e)

		if explore_user:
			self.explore_profile(explore_user)

	def watch_content(self, media: list) -> None:
		if not media:
			return
		explore_user = None
		seen = []
		for m in media[:random.randint(1, len(media))]:
			try:
				logging.info("Watching content with pk '%s'", str(m.id))
				seen.append(str(m.id))
				logging.info("Watched content with id '%s'", str(m.id))
				if random.random() > 0.4:
					explore_user = m.user
					break
				self.random_pause()
			except Exception as e:
				logging.warning("Exception while watching content")
				logging.exception(e)
		try:
			self.scrapler.download_hndlr(self.scrapler.cl.media_seen, seen)
			self.operations_count += 1
		except Exception as e:
			logging.warning("Failed to mark seen watched videos!", exc_info=e)

		if explore_user:
			self.explore_profile(explore_user)

	def scroll_content(self, last_pk: int) -> None:
		timeline_initialized = False
		if random.random() > 0.5:
			timeline_initialized = True
			self.browse_timeline()
			logging.info("Starting to watch related reels with media_pk '%d'", last_pk)
			media = self.scrapler.download_hndlr(self.scrapler.cl.reels, amount=random.randint(4, 10), last_media_pk=last_pk)
			self.operations_count += 1
			self.watch_content(media)
		
		if random.random() > 0.7:
			time.sleep(random.uniform(2, 20))
			if not timeline_initialized:
				self.browse_timeline()
			logging.info("Starting to explore reels with media_pk '%d'", last_pk)
			media = self.scrapler.download_hndlr(self.scrapler.cl.explore_reels, amount=random.randint(4, 10), last_media_pk=last_pk)
			self.operations_count += 1
			self.watch_content(media)

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
			#self.scrapler.timeline_cursor = self.scrapler.download_hndlr(self.scrapler.cl.get_timeline_feed, "pull_to_refresh", self.scrapler.timeline_cursor.get("next_max_id"))
			#self.operations_count += 1
			self.browse_timeline()
			time.sleep(random.uniform(3, 7))
			if random.random() > 0.5:
				self.check_direct()
			#if random.random() > 0.6:
			#	self.scrapler.download_hndlr(self.scrapler.cl.notification_like_and_comment_on_photo_user_tagged, "everyone")
			#	self.operations_count += 1
			#	self.random_pause()
			if random.random() > 0.2:
				logging.info("Simulation updating reels tray feed ...")
				self.scrapler.download_hndlr(self.scrapler.cl.get_reels_tray_feed, "pull_to_refresh")
				self.operations_count += 1
				self.random_pause()
			if random.random() > 0.4:
				self.watch_stories()
			if random.random() > 0.8:
				self.profile_view()
		except Exception as e:
			logging.warning("Error in morning_routine")
			logging.exception(e)

	def daytime_routine(self) -> None:
		try:
			logging.info("Starting day fast check activity simulation")
			#self.scrapler.download_hndlr(self.scrapler.cl.get_timeline_feed, "pull_to_refresh")
			#self.operations_count += 1
			self.browse_timeline()
			time.sleep(random.uniform(2, 5))
			if random.random() > 0.5:
				self.scrapler.download_hndlr(self.scrapler.cl.get_reels_tray_feed, "pull_to_refresh")
				self.operations_count += 1
				self.random_pause()

			if random.random() > 0.4:
				self.watch_stories()
				self.random_pause()

			if random.random() > 0.4:
				logging.info("Watching reels ...")
				reels = self.scrapler.download_hndlr(self.scrapler.cl.reels, amount=random.randint(4, 15))
				self.operations_count += 1
				self.watch_content(reels)
				self.random_pause()
		except Exception as e:
			logging.warning("Error in daytime_routine")
			logging.exception(e)

	def evening_routine(self) -> None:
		try:
			logging.info("Starting evening active user simulation")
			self.browse_timeline()
			time.sleep(random.uniform(2, 5))
			if random.random() > 0.5:
				self.check_direct()
			#if random.random() > 0.6:
			#	logging.info("Checking notifications, tags ...")
			#	self.scrapler.download_hndlr(self.scrapler.cl.notification_like_and_comment_on_photo_user_tagged, "everyone")
			#	self.operations_count += 1
			#	self.random_pause()
			if random.random() > 0.4:
				self.watch_stories()
				self.random_pause()
			if random.random() > 0.4:
				logging.info("Watching reels ...")
				reels = self.scrapler.download_hndlr(self.scrapler.cl.reels, amount=random.randint(4, 10))
				self.operations_count += 1
				self.watch_content(reels)
				self.random_pause()
			if random.random() > 0.4:
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
				self.check_direct()
			if random.random() > 0.7:
				self.watch_stories()
				self.random_pause()
			if random.random() > 0.5:
				logging.info("Watching reels ...")
				reels = self.scrapler.download_hndlr(self.scrapler.cl.reels, amount=random.randint(4, 15))
				self.operations_count += 1
				self.watch_content(reels)
				self.random_pause()
		except Exception as e:
			logging.warning("Error in night_routine")
			logging.exception(e)

	def random_pause(self, short: bool=False) -> None:
		pause = random.uniform(3, 10) if short else random.uniform(10, 30)
		logging.info("Pause for '%.2f' sec ...", round(pause, 2))
		time.sleep(pause)

	def check_direct(self) -> None:
		logging.info("Checking direct ...")
		self.scrapler.download_hndlr(self.scrapler.cl.direct_active_presence)
		self.operations_count += 1
		self.random_pause()
		threads = self.scrapler.download_hndlr(self.scrapler.cl.direct_threads, amount=random.randint(3, 7))
		self.operations_count += 1
		for thread in threads:
			try:
				messages = self.scrapler.cl.direct_messages(thread.id, amount=random.randint(5, 15))
				self.operations_count += 1
				if not messages:
					continue
				msg_sample = random.sample(messages, k=random.randint(1, min(len(messages), 5)))
				for msg in msg_sample:
					if random.random() < 0.85:
						self.scrapler.cl.direct_message_seen(msg.thread_id, msg.id)
						self.operations_count += 1
					self.random_pause()
				self.random_pause()
			except Exception as e:
				logging.warning("Failed to read thread %s", thread.id)
				logging.exception(e)

	def explore_profile(self, user: UserShort) -> None:
		try:
			logging.info("Exploring user profile '%s'", user.username)
			user_id = self.scrapler.download_hndlr(self.scrapler.cl.user_id_from_username, user.username)
			self.operations_count += 1
			if user_id:
				user_medias = self.scrapler.download_hndlr(self.scrapler.cl.user_medias, user_id, amount=random.randint(5, 15), sleep=random.randint(3, 7))
				self.operations_count += 1
				if user_medias:
					self.random_pause(short=True)
					self.watch_content(user_medias)
		except Exception as e:
			logging.warning("Failed to explore user profile with username '%s'", user.username, exc_info=e)

	def profile_view(self) -> None:
		try:
			logging.info("profile_view ...")
			my_user_id = self.scrapler.cl.user_id
			logging.info("user_following ...")
			friends = list(self.scrapler.download_hndlr(self.scrapler.cl.user_following, my_user_id, amount=random.randint(5, 15)).values())
			self.operations_count += 1
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
				self.operations_count += 1
				self.random_pause()
			elif isinstance(random_friend, str):
				target_user_id = self.scrapler.download_hndlr(self.scrapler.cl.user_id_from_username, random_friend)
				logging.info("user_info with target_user_id = '%s' ...", target_user_id)
				#self.scrapler.download_hndlr(self.scrapler.cl.user_info, target_user_id)
				self.scrapler.download_hndlr(self.scrapler.cl.user_info_v1, target_user_id)
				self.operations_count += 1
				self.random_pause()
			
			#self.scrapler.cl.explore_page_media_info

			if random.random() > 0.5:
				self.check_direct()

			#if random.random() > 0.3:
			#	logging.info("Checking notifications, tags ...")
			#	self.scrapler.download_hndlr(self.scrapler.cl.notification_like_and_comment_on_photo_user_tagged, "everyone")
			#	self.operations_count += 1
			#	self.random_pause()
			
			if random.random() > 0.5:
				logging.info("user_medias with target_user_id = '%s' ...", target_user_id)
				self.scrapler.download_hndlr(self.scrapler.cl.user_medias_v1, target_user_id, amount=random.randint(1, 10))
				self.operations_count += 1
				self.random_pause()
		except Exception as e:
			logging.warning("Error in profile view")
			logging.exception(e)
