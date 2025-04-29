import os
import logging
from typing import Callable
import asyncio
import threading
import multiprocessing

from warp_beacon.jobs.types import JobType
from warp_beacon.jobs.upload_job import UploadJob
from warp_beacon.storage import Storage

class AsyncUploader(object):
	__JOE_BIDEN_WAKEUP = None
	threads = None
	allow_loop = True
	job_queue = None
	callbacks = None
	storage = None
	in_process = None
	loop = None
	admin_message_callback = None
	request_yt_auth_callback = None
	pool_size = 1

	def __init__(self,
			loop: asyncio.AbstractEventLoop,
			storage: Storage,
			admin_message_callback: Callable,
			request_yt_auth_callback: Callable,
			pool_size: int=min(32, os.cpu_count() + 4)
		) -> None:
		self.threads = []
		self.callbacks = {}
		self.in_process = set()
		self.storage = storage
		self.loop = loop
		self.job_queue = multiprocessing.Queue()
		self.admin_message_callback = admin_message_callback
		self.request_yt_auth_callback = request_yt_auth_callback
		self.pool_size = pool_size
	
	def __del__(self) -> None:
		self.stop_all()

	def start(self) -> None:
		for _ in range(self.pool_size):
			thread = threading.Thread(target=self.do_work)
			thread.start()
			self.threads.append(thread)

	def add_callback(self, message_id: int, callback: Callable) -> None:
		async def callback_wrap(*args, **kwargs) -> None:
			await callback(*args, **kwargs)
			#self.remove_callback(message_id)
		self.callbacks[message_id] = {"callback": callback_wrap}

	def remove_callback(self, message_id: int) -> None:
		if message_id in self.callbacks:
			logging.debug("Removing callback with message id #%d", message_id)
			del self.callbacks[message_id]

	def stop_all(self) -> None:
		self.allow_loop = False
		if self.threads:
			for i in self.threads:
				t_id = i.native_id
				logging.info("Stopping thread #'%s'", t_id)
				self.job_queue.put(self.__JOE_BIDEN_WAKEUP)
				i.join()
				logging.info("Thread #'%s' stopped", t_id)
		self.threads.clear()

	def is_inprocess(self, uniq_id: str) -> bool:
		return uniq_id in self.in_process
	
	def process_done(self, uniq_id: str) -> None:
		self.in_process.discard(uniq_id)

	def set_inprocess(self, uniq_id: str) -> None:
		self.in_process.add(uniq_id)

	def queue_task(self, job: UploadJob) -> None:
		self.job_queue.put_nowait(job)

	def do_work(self) -> None:
		logging.info("Upload worker started")
		while self.allow_loop:
			try:
				try:
					job = self.job_queue.get()
					if job is self.__JOE_BIDEN_WAKEUP:
						break
					if job.is_message_to_admin and job.message_text and self.admin_message_callback:
						self.loop.call_soon_threadsafe(
							asyncio.create_task,
							self.admin_message_callback(job.message_text, job.account_admins)
						)
						continue
					if job.yt_auth and self.request_yt_auth_callback:
						self.loop.call_soon_threadsafe(
							asyncio.create_task,
							self.request_yt_auth_callback()
						)
						continue

					path = ""
					if job.media_type == JobType.COLLECTION:
						for i in job.media_collection:
							for j in i:
								path += f"{j.local_media_path}; "
					else:
						path = job.local_media_path
	
					in_process = job.in_process
					uniq_id = job.uniq_id
					message_id = job.placeholder_message_id

					if not in_process and not job.job_failed and not job.job_warning and not job.replay:
						logging.info("Accepted upload job, file(s): '%s'", path)

					try:
						if message_id in self.callbacks:
							if job.job_failed:
								logging.info("URL '%s' download failed. Skipping upload job ...", job.url)
								if job.job_failed_msg: # we want to say something to user
									self.loop.call_soon_threadsafe(
										asyncio.create_task,
										self.callbacks[message_id]["callback"](job)
									)
								self.process_done(uniq_id)
								self.remove_callback(message_id)
								continue
							
							if job.replay:
								self.loop.call_soon_threadsafe(
									asyncio.create_task,
									self.callbacks[message_id]["callback"](job)
								)
								self.remove_callback(message_id)
								continue

							if job.job_warning:
								logging.info("Job warning occurred ...")
								if job.job_warning_msg:
									self.loop.call_soon_threadsafe(
										asyncio.create_task,
										self.callbacks[message_id]["callback"](job)
									)
								continue
							if in_process:
								db_list_dicts = self.storage.db_lookup_id(uniq_id)
								if db_list_dicts:
									tg_file_ids = [i["tg_file_id"] for i in db_list_dicts]
									dlds_len = len(db_list_dicts)
									if dlds_len > 1:
										job.tg_file_id = ",".join(tg_file_ids)
										job.media_type = JobType.COLLECTION
									elif dlds_len:
										job.tg_file_id = ",".join(tg_file_ids)
										db_data = db_list_dicts.pop()
										job.media_type = JobType[db_data["media_type"].upper()]
										job.canonical_name = db_data.get("canonical_name", "")
									self.loop.call_soon_threadsafe(
										asyncio.create_task,
										self.callbacks[message_id]["callback"](job)
									)
									self.process_done(uniq_id)
									self.remove_callback(message_id)
								else:
									self.queue_task(job)
							else:
								self.loop.call_soon_threadsafe(
									asyncio.create_task,
									self.callbacks[message_id]["callback"](job)
								)
								self.process_done(uniq_id)
								self.remove_callback(message_id)
						else:
							logging.info("No callback no call!!")
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)
		logging.info("Thread done")
