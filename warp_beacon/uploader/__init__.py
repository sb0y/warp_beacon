import threading
import multiprocessing
#import time
import logging

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from typing import Optional, Callable, Coroutine

from storage import Storage

class AsyncUploader(object):
	threads = []
	allow_loop = True
	job_queue = None
	callbacks = {}
	storage = None
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
			self.threads.append(thread)
			thread.start()

	def add_callback(self, message_id: int, callback: Callable, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
		def callback_wrap(*args, **kwargs) -> None:
			ret = callback(*args, **kwargs)
			self.remove_callback(message_id)
			return ret
		self.callbacks[message_id] = {"callback": callback_wrap, "update": update, "context": context}

	def remove_callback(self, message_id: int) -> None:
		if message_id in self.callbacks:
			del self.callbacks[message_id]

	def stop_all(self) -> None:
		self.allow_loop = False
		for i in self.threads:
			i.join()
		self.threads.clear()

	def queue_task(self, path: str, uniq_id: str, message_id: int, media_info: Optional[dict]=None, item_in_process: bool=False) -> None:
		self.job_queue.put_nowait({"path": path, "message_id": message_id, "uniq_id": uniq_id, "media_info": media_info, "in_process": item_in_process})

	def do_work(self) -> None:
		logging.info("Upload worker started")
		while self.allow_loop:
			try:
				try:
					item = self.job_queue.get()
					path = item["path"]
					in_process = item["in_process"]
					uniq_id = item["uniq_id"]
					message_id = item["message_id"]
					media_info = item["media_info"]
					if not in_process:
						logging.info("Accepted download job, file: '%s'", path)
					try:
						for m_id in self.callbacks.copy():
							if m_id == message_id:
								if in_process:
									tg_id = self.storage.db_lookup_id(uniq_id).get("tg_file_id", None)
									if tg_id:
										logging.info("Performing waited job")
										asyncio.ensure_future(self.callbacks[m_id]["callback"](path, media_info, uniq_id, tg_id), loop=self.loop)
									else:
										self.queue_task(path, uniq_id, message_id, media_info, True)
								else:
									asyncio.ensure_future(self.callbacks[m_id]["callback"](path, media_info, uniq_id), loop=self.loop)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)