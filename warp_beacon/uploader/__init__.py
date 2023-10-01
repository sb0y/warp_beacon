import threading
import multiprocessing
import logging

import asyncio

from typing import Optional, Callable

class AsyncUploader(object):
	threads = []
	allow_loop = True
	job_queue = None
	callback = None

	def __init__(self, pool_size: int=3) -> None:
		self.job_queue = multiprocessing.Queue()
		for _ in range(pool_size):
			thread = threading.Thread(target=lambda: asyncio.run(self.do_work()))
			self.threads.append(thread)
			thread.start()
	
	def __del__(self) -> None:
		pass

	def set_callback(self, callback: Callable) -> None:
		self.callback = callback

	def stop_all(self) -> None:
		self.allow_loop = False
		for i in self.threads:
			i.join()

	def queue_task(self, local_path: str) -> None:
		self.job_queue.put_nowait({"path": local_path})

	async def do_work(self) -> None:
		logging.info("Upload worker started")
		while self.allow_loop:
			try:
				try:
					item = self.job_queue.get()
					local_path = item["path"]
					logging.info("Accepted download job, file: '%s'", local_path)
					try:
						if self.callback:
							await self.callback(local_path)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)