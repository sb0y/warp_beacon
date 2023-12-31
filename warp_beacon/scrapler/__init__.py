from typing import Optional, Callable
import multiprocessing
import time
import logging
from requests.exceptions import ConnectTimeout, HTTPError
from instagrapi.exceptions import MediaNotFound

from mediainfo.video import VideoInfo
from uploader import AsyncUploader
from jobs.download_job import DownloadJob

CONST_CPU_COUNT = multiprocessing.cpu_count()


class AsyncDownloader(object):
	workers = []
	allow_loop = None
	job_queue = multiprocessing.Queue()
	uploader = None
	workers_count = CONST_CPU_COUNT

	def __init__(self, uploader: AsyncUploader, workers_count: int=CONST_CPU_COUNT) -> None:
		self.allow_loop = multiprocessing.Value('i', 1)
		self.uploader = uploader
		self.workers_count = workers_count

	def __del__(self) -> None:
		self.stop_all()

	def start(self) -> None:
		for _ in range(self.workers_count):
			proc = multiprocessing.Process(target=self.do_work)
			self.workers.append(proc)
			proc.start()

	def get_media_info(self, path: str, fr_media_info: dict={}) -> Optional[dict]:
		media_info = None
		try:
			if path:
				video_info = VideoInfo(path)
				media_info = video_info.get_finfo(tuple(fr_media_info.keys()))
				media_info.update(fr_media_info)
				logging.info("Media file info: %s", media_info)
				media_info["thumb"] = video_info.generate_thumbnail()
		except Exception as e:
			logging.error("Failed to process media info!")
			logging.exception(e)

		return media_info

	def do_work(self) -> None:
		logging.info("download worker started")
		while self.allow_loop.value == 1:
			try:
				job = None
				try:
					job = self.job_queue.get()
					actor = None
					try:
						files = []
						if "instagram.com/" in job.url:
							if not job.in_process:
								from scrapler.instagram import InstagramScrapler
								actor = InstagramScrapler()
								while True:
									try:
										logging.info("Downloading URL '%s'", job.url)
										files = actor.download(job.url)
										break
									except ConnectTimeout as e:
										logging.error("ConnectTimeout download error!")
										logging.exception(e)
										time.sleep(2)
									except MediaNotFound as e:
										logging.warning("MediaNotFound occurred!")
										logging.exception(e)
										self.uploader.queue_task(job.to_upload_job(
											job_failed=True,
											job_failed_msg="Unable to access to media under this URL. Seems like the media is private.")
										)
										break

								if files:
									for file in files:
										media_info = {}
										if file["type"] == "video":
											media_info = self.get_media_info(file["local_path"], file["media_info"])
										upload_job = job.to_upload_job(
											local_media_path=file["local_path"], 
											media_info=media_info,
											media_type=file["type"]
										)
										self.uploader.queue_task(upload_job)
							else:
								logging.info("Job already in work in parallel worker. Redirecting job to upload worker.")
								self.uploader.queue_task(job.to_upload_job())
					except HTTPError as e:
						logging.error("HTTP error inside download worker!")
						logging.exception(e)
					except Exception as e:
						logging.error("Error inside download worker!")
						logging.exception(e)
						self.notify_task_failed(job)
						#self.queue_task(url=item["url"], message_id=item["message_id"], item_in_process=item["in_process"], uniq_id=item["uniq_id"])
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

	def queue_task(self, job: DownloadJob) -> str:
		self.job_queue.put_nowait(job)
		return str(job.job_id)
	
	def notify_task_failed(self, job: DownloadJob) -> None:
		self.uploader.queue_task(job.to_upload_job(job_failed=True))