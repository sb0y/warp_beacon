import multiprocessing
import uuid
import logging

class AsyncDownloader(object):
	workers = []
	alow_loop = True
	job_queue = multiprocessing.Queue()
	manager = None
	results = None
	def __init__(self, workers_count: int=multiprocessing.cpu_count()) -> None:
		self.manager = multiprocessing.Manager()
		self.results = self.manager.dict()
		for _ in range(workers_count):
			proc = multiprocessing.Process(target=self.do_work)
			self.workers.append(proc)
			proc.start()

	def __del__(self) -> None:
		self.stop_all()

	def do_work(self) -> None:
		logging.info("download worker started")
		while self.alow_loop:
			try:
				try:
					item = self.job_queue.get()
					actor = None
					try:
						if "instagram" in item["url"]:
							from scrapler.instagram import InstagramScrapler
							actor = InstagramScrapler()
							path = actor.download(item["url"])
							self.results[item["id"]] = str(path)
					except Exception as e:
						logging.exception(e)
				except multiprocessing.queue.Empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside worker!")
				logging.exception(e)

	def stop_all(self) -> None:
		self.alow_loop = False
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

	def wait_result(self, result_id: str) -> str:
		while True:
			#logging.info(self.results)
			if result_id in self.results:
				res = self.results[result_id]
				logging.info(res)
				return str(res)
