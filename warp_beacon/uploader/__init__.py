import threading
import multiprocessing
import time
import logging

import asyncio

from typing import Optional, Callable

class AsyncUploader(object):
	threads = []
	allow_loop = True
	job_queue = None
	callbacks = {}

	def __init__(self, pool_size: int=multiprocessing.cpu_count()) -> None:
		self.job_queue = multiprocessing.Queue()
		for _ in range(pool_size):
			thread = threading.Thread(target=lambda: asyncio.run(self.do_work()))
			self.threads.append(thread)
			thread.start()
	
	def __del__(self) -> None:
		self.stop_all()

	def add_callback(self, message_id: int, callback: Callable) -> None:
		self.callbacks[message_id] = callback

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
						for m_id in self.callbacks.copy():
							if m_id == message_id:
								if in_process:
									success = True
									while success:
										success = await self.callbacks[m_id](path, uniq_id, in_process)
										if success:
											break
										time.sleep(1)
										#if not success:
										#	self.queue_task(path, uniq_id, message_id, in_process)
								else:
									await self.callbacks[m_id](path, uniq_id, in_process)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)