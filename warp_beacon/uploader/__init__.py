import threading
import multiprocessing
import logging

import asyncio

from typing import Optional, Callable

class AsyncUploader(object):
	threads = []
	allow_loop = True
	job_queue = None
	callbacks = []
	callback = None
	in_process_callback = None

	def __init__(self, pool_size: int=3) -> None:
		self.job_queue = multiprocessing.Queue()
		for _ in range(pool_size):
			thread = threading.Thread(target=lambda: asyncio.run(self.do_work()))
			self.threads.append(thread)
			thread.start()
	
	def __del__(self) -> None:
		self.stop_all()

	def add_callback(self, message_id: int, callback: Callable) -> None:
		self.callbacks.append({"message_id": message_id, "callback": callback})

	def stop_all(self) -> None:
		self.allow_loop = False
		for i in self.threads:
			i.join()
		self.threads.clear()

	def queue_task(self, path: str, uniq_id: str, message_id: int, item_in_process: bool=False) -> None:
		self.job_queue.put_nowait({"path": path, "message_id": message_id, "uniq_id": uniq_id, "in_process": item_in_process})

	async def do_work(self) -> None:
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
						for cb in self.callbacks:
							if cb["message_id"] == message_id:
								if in_process:
									success = await cb["callback"](path, uniq_id, in_process)
									if not success:
										self.queue_task(path, uniq_id, message_id, in_process)
								else:
									await cb["callback"](path, uniq_id, in_process)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)