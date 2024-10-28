import os
import time
from random import randrange
import threading
import json

from warp_beacon.jobs import Origin
import warp_beacon

import logging

class IGScheduler(object):
	state_file = "/var/warp_beacon/scheduler_state.json"
	downloader = None
	running = True
	thread = None
	event = None
	state = {"remaining": randrange(8400, 26200)}

	def __init__(self, downloader: warp_beacon.scraper.AsyncDownloader) -> None:
		self.downloader = downloader
		self.event = threading.Event()

	def __del__(self) -> None:
		self.stop()

	def save_state(self) -> None:
		try:
			with open(self.state_file, 'w+', encoding="utf-8") as f:
				f.write(json.dumps(self.state))
		except Exception as e:
			logging.error("Failed to save Scheduler state!")
			logging.exception(e)

	def load_state(self) -> None:
		try:
			if os.path.exists(self.state_file):
				with open(self.state_file, 'r', encoding="utf-8") as f:
					self.state = json.loads(f.read())
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
			self.downloader.queue_task(warp_beacon.jobs.download_job.DownloadJob.build(
				session_validation=True,
				job_origin=Origin.INSTAGRAM
			))
		except Exception as e:
			logging.warning("An error occurred while validating instagram session!")
			logging.exception(e)

		return False

	def do_work(self) -> None:
		logging.info("Scheduler thread started ...")
		self.load_state()
		while self.running:
			try:
				if self.state["remaining"] <= 0:
					self.state["remaining"] = randrange(8400, 26200)
					logging.info("Next scheduler activity in '%s' seconds", self.state["remaining"])

				start_time = time.time()
				self.event.wait(timeout=self.state["remaining"])
				elapsed = time.time() - start_time
				self.state["remaining"] -= elapsed

				if self.running:
					logging.info("Scheduler waking up")
					self.validate_ig_session()
				self.save_state()
			except Exception as e:
				logging.error("An error occurred in scheduler thread!")
				logging.exception(e)
