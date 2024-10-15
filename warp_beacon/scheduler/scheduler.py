import threading

from warp_beacon.jobs import Origin
import warp_beacon

import logging

class IGScheduler(object):
	downloader = None
	running = True
	thread = None
	event = None

	def __init__(self, downloader: warp_beacon.scraper.AsyncDownloader) -> None:
		self.downloader = downloader
		self.event = threading.Event()

	def __del__(self) -> None:
		self.stop()

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
		while self.running:
			try:
				logging.info("Scheduler waking up")
				self.validate_ig_session()
				self.event.wait(timeout=3600)
			except Exception as e:
				logging.error("An error occurred in scheduler thread!")
				logging.exception(e)