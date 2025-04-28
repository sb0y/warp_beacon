import os
import time
from random import randrange
import datetime
import threading
import json

import logging

from warp_beacon.jobs import Origin
import warp_beacon

class IGScheduler(object):
	state_file = "/var/warp_beacon/scheduler_state.json"
	yt_sessions_dir = "/var/warp_beacon"
	downloader = None
	running = True
	thread = None
	event = None
	state = {"remaining": randrange(8400, 26200), "yt_sess_exp": []}

	def __init__(self, downloader: warp_beacon.scraper.AsyncDownloader) -> None:
		self.downloader = downloader
		self.event = threading.Event()
		self.handle_time_planning()

	def __del__(self) -> None:
		self.stop()

	def save_state(self) -> None:
		try:
			with open(self.state_file, 'w+', encoding="utf-8") as f:
				f.write(json.dumps(self.state))
		except Exception as e:
			logging.error("Failed to save Scheduler state!")
			logging.exception(e)

	def load_yt_sessions(self) -> None:
		try:
			# old versions migration
			if not "yt_sess_exp" in self.state:
				self.state["yt_sess_exp"] = []
			
			for f in os.listdir(self.yt_sessions_dir):
				if f.startswith("yt_session") and f.endswith(".json"):
					yt_sess_file = f"{self.yt_sessions_dir}/{f}"
					if os.path.exists(yt_sess_file):
						with open(yt_sess_file, 'r', encoding="utf-8") as f:
							yt_sess_data = json.loads(f.read())
							exp = yt_sess_data.get("expires", "")
							self.state["yt_sess_exp"].append({
								"expires": exp,
								"file_path": yt_sess_file,
								"access_token": yt_sess_data.get("access_token", ""),
								"refresh_token": yt_sess_data.get("refresh_token", ""),
								"expires_in": yt_sess_data.get("expires_in", ""),
							})
		except Exception as e:
			logging.error("Failed to load yt sessions!")
			logging.exception(e)

	def load_state(self) -> None:
		try:
			if os.path.exists(self.state_file):
				with open(self.state_file, 'r', encoding="utf-8") as f:
					self.state = json.loads(f.read())
				self.handle_time_planning()
				logging.info("Next scheduler activity in '%d' seconds", int(self.state["remaining"]))
			self.load_yt_sessions()
		except Exception as e:
			logging.error("Failed to load Scheduler state!")
			logging.exception(e)

	def start(self) -> None:
		self.thread = threading.Thread(target=self.do_work)
		self.thread.start()

	def stop(self) -> None:
		self.running = False
		self.event.set()
		if self.thread:
			t_id = self.thread.native_id
			logging.info("Stopping scheduler thread #'%s'", t_id)
			self.thread.join()
			logging.info("Scheduler thread #'%s' stopped", t_id)
			self.thread = None

	def post_image(self, image) -> None:
		pass

	def post_story(self) -> None:
		pass

	def download_random_image(self) -> None:
		pass

	def validate_ig_session(self) -> bool:
		try:
			logging.info("Setting IG validate task ...")
			self.downloader.queue_task(warp_beacon.jobs.download_job.DownloadJob.build(
				session_validation=True,
				job_origin=Origin.INSTAGRAM
			))
			return True
		except Exception as e:
			logging.warning("An error occurred while validating instagram session!")
			logging.exception(e)

		return False
	
	def validate_yt_session(self) -> bool:
		try:
			logging.info("Setting YT validate task ...")
			self.downloader.queue_task(warp_beacon.jobs.download_job.DownloadJob.build(
				session_validation=True,
				job_origin=Origin.YOUTUBE
			))
			return True
		except Exception as e:
			logging.warning("An error occurred while validating instagram session!")
			logging.exception(e)

		return False

	def yt_nearest_expire(self) -> int:
		return int(min(self.state["yt_sess_exp"], key=lambda x: x.get("expires", 0)).get("expires", 0))

	def handle_time_planning(self) -> None:
		if int(self.state.get("remaining", 0)) <= 0:
			self.state["remaining"] = randrange(9292, 26200)

	def do_work(self) -> None:
		logging.info("Scheduler thread started ...")
		self.load_state()
		while self.running:
			try:
				yt_expires = self.yt_nearest_expire()
				ig_sched = self.state["remaining"]
				min_val = min(yt_expires, ig_sched)
				#max_val = max(yt_expires, ig_sched)
				now = datetime.datetime.now()
				if 3 <= now.hour < 7 and min_val != yt_expires:
					logging.info("Scheduler is paused due to night hours (3:00 - 7:00)")
					self.state["remaining"] = 14400
					self.save_state()

				if ig_sched <= 0:
					self.handle_time_planning()

				start_time = time.time()
				logging.info("Next scheduler activity in '%s' seconds", int(min_val))
				logging.info("IG timeout '%d' secs", int(self.state["remaining"]))
				self.event.wait(timeout=min_val)
				self.event.clear()
				elapsed = time.time() - start_time
				self.state["remaining"] -= elapsed

				if self.running:
					if self.state["remaining"] <= 0:
						self.validate_ig_session()
					if yt_expires <= time.time() + 60:
						self.validate_yt_session()
				self.save_state()
			except Exception as e:
				logging.error("An error occurred in scheduler thread!")
				logging.exception(e)
