from typing import Optional, Callable
import multiprocessing
import uuid
import logging

from uploader import AsyncUploader

CONST_CPU_COUNT = multiprocessing.cpu_count()


class AsyncDownloader(object):
	workers = []
	allow_loop = None
	job_queue = multiprocessing.Queue()
	manager = None
	results = None
	uploader = None
	def __init__(self, uploader: AsyncUploader, workers_count: int=CONST_CPU_COUNT) -> None:
		self.manager = multiprocessing.Manager()
		self.results = self.manager.dict()
		self.allow_loop = multiprocessing.Value('i', 1)
		self.uploader = uploader
		for _ in range(workers_count):
			proc = multiprocessing.Process(target=self.do_work)
			self.workers.append(proc)
			proc.start()

	def __del__(self) -> None:
		self.stop_all()

	def do_work(self) -> None:
		logging.info("download worker started")
		while self.allow_loop.value == 1:
			#current_task_id = ""
			try:
				try:
					item = self.job_queue.get()
					actor = None
					try:
						if "instagram" in item["url"]:
							from scrapler.instagram import InstagramScrapler
							actor = InstagramScrapler()
							#current_task_id = item["id"]
							path = actor.download(item["url"])
							self.uploader.queue_task(path)
							#self.results[current_task_id] = str(path)
					except Exception as e:
						#self.results[current_task_id] = None
						logging.exception(e)
				except multiprocessing.queue.Empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside worker!")
				logging.exception(e)

	def stop_all(self) -> None:
		self.allow_loop.value = 0
		for proc in self.workers:
			if proc.is_alive():
				logging.info("stopping process #%d", proc.pid)
				proc.terminate()
				proc.join()
				logging.info("process #%d stopped", proc.pid)

	def queue_task(self, url: str) -> str:
		id = uuid.uuid4()
		self.job_queue.put_nowait({"url": url, "id": id})
		return id

	def wait_result(self, result_id: str) -> Optional[str]:
		while self.allow_loop.value == 1:
			if result_id in self.results:
				res = self.results[result_id]
				logging.info("local file: %s", res)
				return res

		return None