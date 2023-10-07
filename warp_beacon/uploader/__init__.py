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

	def __init__(self, loop: asyncio.AbstractEventLoop, storage: Storage, pool_size: int=multiprocessing.cpu_count()) -> None:
		self.storage = storage
		self.loop = loop
		self.job_queue = multiprocessing.Queue()
		#do_work = lambda: asyncio.run(self.do_work())
		for _ in range(pool_size):
			thread = threading.Thread(target=self.do_work)
			self.threads.append(thread)
			thread.start()
	
	def __del__(self) -> None:
		self.stop_all()

	def add_callback(self, message_id: int, callback: Callable, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
		def callback_wrap() -> None:
			ret = callback()
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

	def queue_task(self, path: str, uniq_id: str, message_id: int, item_in_process: bool=False) -> None:
		self.job_queue.put_nowait({"path": path, "message_id": message_id, "uniq_id": uniq_id, "in_process": item_in_process})

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
					if not in_process:
						logging.info("Accepted download job, file: '%s'", path)
					try:
						for m_id in self.callbacks.copy():
							if m_id == message_id:
								if in_process:
									tg_id = None
									doc = self.storage.db_lookup_id(uniq_id=uniq_id)
									if doc:
										try:
											tg_id = doc["tg_file_id"]
										except Exception as e:
											logging.error("DB error!")
											logging.exception(e)
									if tg_id:
										logging.info("Performing wait job")
										asyncio.ensure_future(self.callbacks[m_id]["callback"](self.callbacks[m_id]["update"], self.callbacks[m_id]["context"], path, uniq_id, tg_id), loop=self.loop)
									else:
										self.queue_task(path, uniq_id, message_id, True)
								else:
									asyncio.ensure_future(self.callbacks[m_id]["callback"](self.callbacks[m_id]["update"], self.callbacks[m_id]["context"], path, uniq_id), loop=self.loop)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)