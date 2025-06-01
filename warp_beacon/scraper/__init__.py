import logging
import multiprocessing
import multiprocessing.connection
import os
import time
from multiprocessing.managers import Namespace
from queue import Empty
from typing import Optional

from warp_beacon.compress.video import VideoCompress
from warp_beacon.jobs import Origin
from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.jobs.types import JobType
from warp_beacon.jobs.upload_job import UploadJob
from warp_beacon.mediainfo.audio import AudioInfo
from warp_beacon.mediainfo.silencer import Silencer
from warp_beacon.mediainfo.video import VideoInfo
from warp_beacon.scraper.account_selector import AccountSelector
from warp_beacon.scraper.exceptions import (AllAccountsFailed, BadProxy,
											CaptchaIssue, FileTooBig,
											IGRateLimitOccurred, NotFound,
											TimeOut, Unavailable, UnknownError,
											YotubeAgeRestrictedError,
											YoutubeLiveError)
from warp_beacon.scraper.fail_handler import FailHandler
from warp_beacon.scraper.link_resolver import LinkResolver
from warp_beacon.storage.mongo import DBClient
from warp_beacon.uploader import AsyncUploader

ACC_FILE = os.environ.get("SERVICE_ACCOUNTS_FILE", default="/var/warp_beacon/accounts.json")
PROXY_FILE = os.environ.get("PROXY_FILE", default="/var/warp_beacon/proxies.json")

class AsyncDownloader(object):
	TG_FILE_LIMIT = 2147483648 # 2 GiB
	__JOE_BIDEN_WAKEUP = None

	def __init__(self, uploader: AsyncUploader, pipe_connection: multiprocessing.connection.Connection, workers_count: int) -> None:
		self.workers = []
		self.job_queue = multiprocessing.Queue()
		self.auth_event = multiprocessing.Event()
		self.manager = multiprocessing.Manager()
		self.process_context = self.manager.Namespace()
		self.allow_loop = self.manager.Value('i', 1)
		self.scrolling_now = self.manager.Value('i', 0)
		self.acc_selector = AccountSelector(self.manager, ACC_FILE, PROXY_FILE)
		self.uploader = uploader
		self.workers_count = workers_count
		self.status_pipe = pipe_connection
		self.yt_validate_event = multiprocessing.Event()
		if os.environ.get("TG_PREMIUM", default="false") == "true":
			self.TG_FILE_LIMIT = 4294967296 # 4 GiB

	def start(self) -> None:
		for _ in range(self.workers_count):
			proc = multiprocessing.Process(target=self.do_work, args=(self.acc_selector, self.process_context))
			self.workers.append(proc)
			proc.start()

	def get_media_info(self, path: str, fr_media_info: dict={}, media_type: JobType = JobType.VIDEO) -> Optional[dict]:
		media_info = None
		try:
			if path:
				if media_type == JobType.VIDEO:
					video_info = VideoInfo(path)
					media_info = video_info.get_finfo(tuple(fr_media_info.keys()))
					if fr_media_info:
						media_info.update(fr_media_info)
					if not media_info.get("thumb", None):
						media_info["thumb"] = video_info.generate_thumbnail()
					media_info["has_sound"] = video_info.has_sound()
				elif media_type == JobType.AUDIO:
					audio_info = AudioInfo(path)
					media_info = audio_info.get_finfo(tuple(fr_media_info.keys()))
		except Exception as e:
			logging.error("Failed to process media info!")
			logging.exception(e)

		return media_info

	def try_next_account(self, selector: AccountSelector, job: DownloadJob, report_error: str = None) -> None:
		logging.warning("Switching account!")
		if report_error:
			selector.bump_acc_fail(report_error)
		selector.next()
		cur_acc = selector.get_current()
		logging.info("Current account: '%s'", str(cur_acc))
		job.account_switches += 1
		selector.reset_ig_request_count()

	def do_work(self, selector: AccountSelector, _: Namespace) -> None:
		logging.info("download worker started")
		# pymongo is not fork-safe so new connect to DB required
		fail_handler = FailHandler(DBClient())
		last_proxy = None
		while self.allow_loop.value == 1:
			try:
				job: DownloadJob = None
				actor = None
				try:
					job = self.job_queue.get()
					if job is self.__JOE_BIDEN_WAKEUP:
						break
					try:
						items = []
						if job.job_origin is Origin.UNKNOWN:
							logging.warning("Unknown task origin! Skipping.")
							continue
						if LinkResolver.resolve_job(job):
							self.uploader.queue_task(job.to_upload_job(
								replay=True
							))
							continue
		
						if job.account_switches > self.acc_selector.count_service_accounts(job.job_origin):
							raise AllAccountsFailed("All config accounts failed!", job=job)
						if not job.in_process:
							if job.job_postponed_until > 0:
								if (job.job_postponed_until - time.time()) > 0:
									logging.warning("Job '%s' is postponed, rescheduling", job.url)
									time.sleep(2)
									self.job_queue.put(job)
									continue
							last_proxy = selector.get_last_proxy()
							selector.set_module(job.job_origin)
							# use same proxy as in content request before
							proxy = None
							if job.scroll_content:
								proxy = last_proxy
								logging.info("Chosen last proxy '%s'", proxy)
							else:
								proxy = selector.get_current_proxy()
							if job.job_origin is Origin.INSTAGRAM:
								from warp_beacon.scraper.instagram.instagram import InstagramScraper
								ig_requests_limit = int(os.environ.get("IG_REQUESTS_PER_ACCOUNT", default="20"))
								ig_requests = selector.get_ig_request_count()
								if not job.scroll_content and ig_requests >= ig_requests_limit:
									logging.info("The account requests limit '%d' has been reached value '%d'. Selecting the next account.", ig_requests_limit, ig_requests)
									selector.reset_ig_request_count()
									selector.next()
								actor = InstagramScraper(client_session_id=selector.get_ig_session_id(), account=selector.get_current(), proxy=proxy)
								selector.inc_ig_request_count()
							elif job.job_origin is Origin.YT_SHORTS:
								from warp_beacon.scraper.youtube.shorts import YoutubeShortsScraper
								actor = YoutubeShortsScraper(selector.get_current(), proxy)
							elif job.job_origin is Origin.YT_MUSIC:
								from warp_beacon.scraper.youtube.music import YoutubeMusicScraper
								actor = YoutubeMusicScraper(selector.get_current(), proxy)
							elif job.job_origin is Origin.YOUTUBE:
								from warp_beacon.scraper.youtube.youtube import YoutubeScraper
								actor = YoutubeScraper(selector.get_current(), proxy)
							elif job.job_origin is Origin.X:
								from warp_beacon.scraper.X.X import XScraper
								actor = XScraper(selector.get_current(), proxy)

							actor.send_message_to_admin_func = self.send_message_to_admin
							actor.request_yt_auth = self.request_yt_auth
							actor.auth_event = self.auth_event
							actor.status_pipe = self.status_pipe
							actor.yt_validate_event = self.yt_validate_event
							actor.acc_selector = selector
							# job retry loop
							while self.allow_loop.value == 1:
								try:
									if job.scroll_content and job.last_pk and job.job_origin is Origin.INSTAGRAM:
										self.scrolling_now.value = 1
										logging.info("Scrolling relative content with pk '%s'", job.last_pk)
										operations = actor.scroll_content(last_pk=job.last_pk)
										if operations:
											selector.inc_ig_request_count(amount=operations)
										self.scrolling_now.value = 0
										logging.info("Scrolling done")
										break
									if job.session_validation and job.job_origin in (Origin.INSTAGRAM, Origin.YOUTUBE):
										if job.job_origin is Origin.INSTAGRAM:
											ig_requests_limit = int(os.environ.get("IG_REQUESTS_PER_ACCOUNT", default="20"))
											if selector.get_ig_request_count() >= ig_requests_limit:
												ig_requests = selector.get_ig_request_count()
												logging.info("The account requests limit '%d' has been reached value '%d'. Selecting the next account.", ig_requests_limit, ig_requests)
												selector.reset_ig_request_count()
												selector.next()
										logging.info("Validating '%s' session ...", job.job_origin.value)
										operations = actor.validate_session()
										if job.job_origin is Origin.INSTAGRAM and operations:
											selector.inc_ig_request_count(amount=operations)
										logging.info("Validation done")
									else:
										logging.info("Downloading URL '%s'", job.url)
										items = actor.download(job)
									break
								except NotFound as e:
									logging.warning("Not found error occurred!")
									logging.exception(e)
									self.send_message_to_admin(
										f"Task <code>{job.job_id}</code> failed. URL: {job.url}'. Reason: '<b>NotFound</b>'."
									)
									self.uploader.queue_task(job.to_upload_job(
										job_failed=True,
										job_failed_msg="Unable to access to media under this URL. Seems like the media is private.")
									)
									break
								except Unavailable as e:
									logging.warning("Not found or unavailable error occurred!")
									logging.exception(e)
									if job.unvailable_error_count > selector.count_service_accounts(job.job_origin):
										self.uploader.queue_task(job.to_upload_job(
											job_failed=True,
											job_failed_msg="Video is unvailable for all your service accounts.")
										)
										break
									job.unvailable_error_count += 1
									logging.info("Trying to switch account")
									selector.next()
									self.job_queue.put(job)
									break
								except (TimeOut, BadProxy) as e:
									logging.warning("Timeout or BadProxy error occurred!")
									logging.exception(e)
									if job.bad_proxy_error_count > len(selector.proxies):
										self.send_message_to_admin(
											f"Task <code>{job.job_id}</code> failed. URL: '{job.url}'. Reason: '<b>TimeOut</b>'."
										)
										self.uploader.queue_task(job.to_upload_job(
											job_failed=True,
											job_failed_msg="Failed to download content due timeout error. Please check you Internet connection, retry amount or request timeout bot configuration settings.")
										)
										break
									job.bad_proxy_error_count += 1
									logging.info("Trying next proxy")
									selector.next_proxy()
									self.job_queue.put(job)
								except FileTooBig as e:
									logging.warning("Telegram limits exceeded :(")
									logging.exception(e)
									self.send_message_to_admin(
										f"Task <code>{job.job_id}</code> failed. URL: '{job.url}'. Reason: '<b>FileTooBig</b>'."
									)
									self.uploader.queue_task(job.to_upload_job(
										job_failed=True,
										job_failed_msg="Unfortunately this file has exceeded the Telegram limits. A file cannot be larger than 2 gigabytes.")
									)
									break
								except IGRateLimitOccurred as e:
									logging.warning("IG ratelimit occurred :(")
									logging.exception(e)
									self.try_next_account(selector, job, report_error="rate_limits")
									self.job_queue.put(job)
									break
								except CaptchaIssue as e:
									logging.warning("Challange occurred!")
									logging.exception(e)
									acc_index, acc_data = selector.get_current()
									self.send_message_to_admin(
										f"Captcha required for account #{acc_index}, login: '{acc_data.get('login', 'unknown')}'."
									)
									self.try_next_account(selector, job, report_error="captcha")
									self.job_queue.put(job)
									break
								except YoutubeLiveError as e:
									logging.warning("Youtube Live videos are not supported. Skipping.")
									logging.exception(e)
									self.uploader.queue_task(job.to_upload_job(
										job_failed=True,
										job_failed_msg="Youtube Live videos are not supported. Please wait until the live broadcast ends.")
									)
									break
								except YotubeAgeRestrictedError as e:
									logging.error("Youtube Age Restricted error")
									logging.exception(e)
									self.uploader.queue_task(job.to_upload_job(
										job_failed=True,
										job_failed_msg="Youtube Age Restricted error. Check your bot Youtube account settings.")
									)
									self.send_message_to_admin(
										f"Task <code>{job.job_id}</code> failed. URL: '{job.url}'. Reason: '<b>YotubeAgeRestrictedError</b>'."
									)
									break
								except (UnknownError, Exception) as e:
									logging.warning("UnknownError occurred!")
									logging.exception(e)
									exception_msg = ""
									if hasattr(e, "message"):
										exception_msg = e.message
									else:
										exception_msg = str(e)
									if "geoblock_required" in exception_msg:
										if job.geoblock_error_count > self.acc_selector.count_service_accounts(job.job_origin):
											self.send_message_to_admin(
												f"Task <code>{job.job_id}</code> failed. URL: '{job.url}'. Reason: '<b>geoblock_required</b>'."
											)
											self.uploader.queue_task(job.to_upload_job(
												job_failed=True,
												job_failed_msg="This content does not accessible for all yout bot accounts. Seems like author blocked certain regions.")
											)
											break
										job.geoblock_error_count += 1
										logging.info("Trying to switch account")
										self.acc_selector.next()
										self.job_queue.put(job)
										break
									self.send_message_to_admin(
										f"Task <code>{job.job_id}</code> failed. URL: {job.url}. Reason: '<b>UnknownError</b>'."
										f"Exception:\n<pre code=\"python\">{exception_msg}\n</pre>"
									)
									self.uploader.queue_task(job.to_upload_job(
										job_failed=True,
										job_failed_msg=f"Unknown error occurred. Please <a href=\"https://github.com/sb0y/warp_beacon/issues\">create issue</a> with service logs.\n"
										f"Task <code>{job.job_id}</code> failed. URL: {job.url}.\n"
										f"Reason: '<b>UnknownError</b>'.\n"
										f"Exception:\n<pre code=\"python\">{exception_msg}</pre>"
									))
									break
								finally:
									if actor:
										actor.restore_gai()

							last_proxy = proxy

							if items:
								# success
								for job in fail_handler.get_failed_jobs():
									self.queue_task(job)
								for item in items:
									media_info = {"filesize": 0}
									if item["media_type"] == JobType.VIDEO:
										media_info_tmp = item.get("media_info", {})
										media_info_tmp["thumb"] = item.get("thumb", None)
										media_info = self.get_media_info(item["local_media_path"], media_info_tmp, JobType.VIDEO)
										logging.info("Final media info: %s", media_info)
										if media_info["filesize"] > self.TG_FILE_LIMIT:
											logging.info("Filesize is '%d' MiB", round(media_info["filesize"] / 1024 / 1024))
											logging.info("Detected big file. Starting compressing with ffmpeg ...")
											self.uploader.queue_task(job.to_upload_job(
												job_warning=True,
												job_warning_msg="Downloaded file size is bigger than Telegram limits! Performing video compression. This may take a while.")
											)
											ffmpeg = VideoCompress(file_path=item["local_media_path"])
											new_filepath = ffmpeg.generate_filepath(base_filepath=item["local_media_path"])
											target_size = 2000 * 1000
											if os.environ.get("TG_PREMIUM", default="false") == "true":
												target_size = 4000 * 1000
											if ffmpeg.compress_to(new_filepath, target_size=target_size):
												logging.info("Successfully compressed file '%s'", new_filepath)
												os.unlink(item["local_media_path"])
												item["local_media_path"] = new_filepath
												item["local_compressed_media_path"] = new_filepath
												media_info["filesize"] = VideoInfo.get_filesize(new_filepath)
												logging.info("New file size of compressed file is '%.3f'", media_info["filesize"])
										if not media_info["has_sound"]:
											item["media_type"] = JobType.ANIMATION
									elif item["media_type"] == JobType.AUDIO:
										media_info = self.get_media_info(item["local_media_path"], item.get("media_info", {}), JobType.AUDIO)
										media_info["performer"] = item.get("performer", None)
										media_info["thumb"] = item.get("thumb", None)
										logging.info("Final media info: %s", media_info)
									elif item["media_type"] == JobType.COLLECTION:
										for chunk in item["items"]:
											for v in chunk:
												if v["media_type"] == JobType.VIDEO:
													col_media_info = self.get_media_info(v["local_media_path"], v["media_info"])
													media_info["filesize"] += int(col_media_info.get("filesize", 0))
													v["media_info"] = col_media_info
													if not v["media_info"]["has_sound"]:
														silencer = Silencer(v["local_media_path"])
														silent_video_path = silencer.add_silent_audio()
														os.unlink(v["local_media_path"])
														v["local_media_path"] = silent_video_path
														v["media_info"].update(silencer.get_finfo())
														v["media_info"]["has_sound"] = True

									job_args = {"media_type": item["media_type"], "media_info": media_info}
									if item["media_type"] == JobType.COLLECTION:
										job_args["media_collection"] = item["items"]
										if item.get("save_items", None) is not None:
											job_args["save_items"] = item.get("save_items", False)
									else:
										job_args["local_media_path"] = item["local_media_path"]
										if item.get("local_compressed_media_path", None):
											job_args["local_media_path"] = item.get("local_compressed_media_path", None)

									job_args["canonical_name"] = item.get("canonical_name", "")

									logging.debug("local_media_path: '%s'", job_args.get("local_media_path", ""))
									logging.debug("media_collection: '%s'", str(job_args.get("media_collection", {})))
									#logging.info(job_args)
									upload_job = job.to_upload_job(**job_args)
									if upload_job.is_empty():
										logging.info("Upload job is empty. Nothing to do here!")
										self.uploader.queue_task(job.to_upload_job(
											job_failed=True,
											job_failed_msg="Seems like this link doesn't contains any media.")
										)
									else:
										self.uploader.queue_task(upload_job)
									# watch related reels to simulate human
									if self.scrolling_now.value == 0:
										if item.get("last_pk", 0) and "reel/" in job.url:
											self.queue_task(DownloadJob.build(
												scroll_content=True,
												last_pk=int(item.get("last_pk", 0)),
												job_origin=Origin.INSTAGRAM
											))
									else:
										logging.info("Scrolling in progress, ignoring request")
								
								# report media seen
								if job.job_origin is Origin.INSTAGRAM:
									actor.report_seen(items)
						else:
							logging.info("Job already in work in parallel worker. Redirecting job to upload worker.")
							self.uploader.queue_task(job.to_upload_job())
					except AllAccountsFailed as e:
						self.send_message_to_admin(
							f"Task <code>{job.job_id}</code> failed. URL: '{job.url}'. Reason: '<b>AllAccountsFailed</b>'."
						)
						if job.job_origin == Origin.INSTAGRAM:
							logging.info("Handling captcha postpone")
							self.uploader.queue_task(job.to_upload_job(
								job_warning=True,
								job_warning_msg="The bot is currently experiencing technical issues. Message delivery may be delayed.")
							)
							#self.try_next_account(selector, job, report_error="captcha")
							#e.job.job_postponed_until = time.time() + 300
							#self.job_queue.put(e.job)
							fail_handler.store_failed_job(job)
							self.notify_task_failed(job)
					except Exception as e:
						logging.error("Error inside download worker!")
						logging.exception(e)
						self.notify_task_failed(job)
				except Empty:
					pass
			except Exception as e:
				logging.error("Exception occurred inside worker!")
				logging.exception(e)

		logging.info("Process done")

	def stop_all(self) -> None:
		self.allow_loop.value = 0
		self.acc_selector.save_state()
		for proc in self.workers:
			if proc.is_alive():
				logging.info("stopping process #%d", proc.pid)
				self.job_queue.put_nowait(self.__JOE_BIDEN_WAKEUP)
				proc.join()
				#proc.terminate()
				logging.info("process #%d stopped", proc.pid)
		self.workers.clear()
		self.manager.shutdown()

	def queue_task(self, job: DownloadJob) -> str:
		self.job_queue.put_nowait(job)
		return str(job.job_id)
	
	def notify_task_failed(self, job: DownloadJob) -> None:
		self.uploader.queue_task(job.to_upload_job(job_failed=True))

	def send_message_to_admin(self, text: str, account_admins: str = None, _: object = None) -> None:
		self.uploader.queue_task(UploadJob.build(
			is_message_to_admin=True,
			message_text=text,
			account_admins=account_admins
		))

	def request_yt_auth(self) -> None:
		self.uploader.queue_task(UploadJob.build(yt_auth=True))