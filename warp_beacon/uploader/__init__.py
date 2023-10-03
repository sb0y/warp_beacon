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
	in_process_callback = None

	def __init__(self, pool_size: int=3) -> None:
		self.job_queue = multiprocessing.Queue()
		for _ in range(pool_size):
			thread = threading.Thread(target=lambda: asyncio.run(self.do_work()))
			self.threads.append(thread)
			thread.start()
	
	def __del__(self) -> None:
		self.stop_all()

	def set_send_video_callback(self, callback: Callable) -> None:
		self.callback = callback

	def set_in_process_callback(self, callback: Callable) -> None:
		self.in_process_callback = callback

	def stop_all(self) -> None:
		self.allow_loop = False
		for i in self.threads:
			i.join()
		self.threads.clear()

	def queue_task(self, path: str, uniq_id: str, effective_message_id: int, item_in_process: bool=False) -> None:
		self.job_queue.put_nowait({"path": path, "uniq_id": uniq_id, "in_process": item_in_process, 
			"effective_message_id": effective_message_id}
		)

	async def do_work(self) -> None:
		logging.info("Upload worker started")
		while self.allow_loop:
			try:
				try:
					item = self.job_queue.get()
					path = item["path"]
					in_process = item["in_process"]
					uniq_id = item["uniq_id"]
					effective_message_id = item["effective_message_id"]
					if not in_process:
						logging.info("Accepted download job, file: '%s'", path)
					try:
						if in_process:
							if self.in_process_callback:
								success = await self.in_process_callback(uniq_id, effective_message_id)
								if not success:
									self.queue_task(path, uniq_id, effective_message_id, in_process)
						else:
							if self.callback:
								await self.callback(path, uniq_id, effective_message_id)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.Queue.empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside upload worker!")
				logging.exception(e)