from typing import Optional, Callable
import multiprocessing
import time
import uuid
import logging
from requests.exceptions import ConnectTimeout

from uploader import AsyncUploader

CONST_CPU_COUNT = multiprocessing.cpu_count()


class AsyncDownloader(object):
	workers = []
	allow_loop = None
	job_queue = multiprocessing.Queue()
	uploader = None

	def __init__(self, uploader: AsyncUploader, workers_count: int=CONST_CPU_COUNT) -> None:
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
			try:
				try:
					item = self.job_queue.get()
					actor = None
					try:
						if "instagram" in item["url"]:
							if not item["in_process"]:
								from scrapler.instagram import InstagramScrapler
								actor = InstagramScrapler()
								while True:
									try:
										path = actor.download(item["url"])
										break
									except ConnectTimeout as e:
										logging.error("ConnectTimeout download error!")
										logging.exception(e)
										time.sleep(2)

								self.uploader.queue_task(path=str(path), message_id=item["message_id"], uniq_id=item["uniq_id"])
							else:
								logging.info("Job already in work in parallel worker. Redirecting job to upload worker.")
								self.uploader.queue_task(path=item["url"], message_id=item["message_id"], uniq_id=item["uniq_id"], item_in_process=True)
					except Exception as e:
						logging.error("Error inside download worker!")
						logging.exception(e)
						self.queue_task(url=item["url"], item_in_process=item["in_process"], uniq_id=item["uniq_id"])
				except multiprocessing.Queue.empty:
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
		self.workers.clear()

	def queue_task(self, url: str, uniq_id: str, message_id: str, item_in_process: str=False) -> str:
		id = uuid.uuid4()
		self.job_queue.put_nowait({"url": url, "id": id, "in_process": item_in_process, "uniq_id": uniq_id, "message_id": message_id})
		return id