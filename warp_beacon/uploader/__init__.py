import threading
import multiprocessing
from warp_beacon.jobs.upload_job import UploadJob
#import time
import logging

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from typing import Optional, Callable, Coroutine

from warp_beacon.storage import Storage

class AsyncUploader(object):
	__JOE_BIDEN_WAKEUP = None
	threads = []
	allow_loop = True
	job_queue = None
	callbacks = {}
	storage = None
	in_process = set()
	loop = None
	pool_size = 1

	def __init__(self, loop: asyncio.AbstractEventLoop, storage: Storage, pool_size: int=multiprocessing.cpu_count()) -> None:
		self.storage = storage
		self.loop = loop
		self.job_queue = multiprocessing.Queue()
		self.pool_size = pool_size
	
	def __del__(self) -> None:
		self.stop_all()

	def start(self) -> None:
		for _ in range(self.pool_size):
			thread = threading.Thread(target=self.do_work)
			thread.start()
			self.threads.append(thread)

	def add_callback(self, message_id: int, callback: Callable, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
		def callback_wrap(*args, **kwargs) -> None:
			ret = callback(*args, **kwargs)
			#self.remove_callback(message_id)
			return ret
		self.callbacks[message_id] = {"callback": callback_wrap, "update": update, "context": context}

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
						continue
					path = ""
					if job.media_type == "collection":
						for i in job.media_collection:
							path += "%s; " % i.local_media_path
					else:
						path = job.local_media_path
					in_process = job.in_process
					uniq_id = job.uniq_id
					message_id = job.placeholder_message_id
					if not in_process and  not job.job_failed and not job.job_warning:
						logging.info("Accepted upload job, file(s): '%s'", path)
					try:
						if message_id in self.callbacks:
							if job.job_failed:
								logging.info("URL '%s' download failed. Skipping upload job ...", job.url)
								if job.job_failed_msg: # we want to say something to user
									asyncio.ensure_future(self.callbacks[message_id]["callback"](job), loop=self.loop)
								self.process_done(uniq_id)
								self.remove_callback(message_id)
								continue
							if job.job_warning:
								logging.info("Job warning occurred ...")
								if job.job_warning_msg:
									asyncio.ensure_future(self.callbacks[message_id]["callback"](job), loop=self.loop)
								continue
							if in_process:
								db_list_dicts = self.storage.db_lookup_id(uniq_id)
								if db_list_dicts:
									tg_file_ids = [i["tg_file_id"] for i in db_list_dicts]
									dlds_len = len(db_list_dicts)
									if dlds_len > 1:
										job.tg_file_id = ",".join(tg_file_ids)
										job.media_type = "collection"
									elif dlds_len:
										job.tg_file_id = ",".join(tg_file_ids)
										job.media_type = db_list_dicts.pop()["media_type"]
									asyncio.ensure_future(self.callbacks[message_id]["callback"](job), loop=self.loop)
									self.process_done(uniq_id)
									self.remove_callback(message_id)
								else:
									self.queue_task(job)
							else:
								asyncio.ensure_future(self.callbacks[message_id]["callback"](job), loop=self.loop)
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
