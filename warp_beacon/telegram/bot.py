import os, io
import signal

import uvloop
import asyncio

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, InputMedia, InputMediaAudio, InputMediaPhoto, InputMediaVideo, InputMediaAnimation, InputMediaDocument, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import RPCError, FloodWait, NetworkMigrate, BadRequest, MultiMediaTooLong, MessageIdInvalid

from warp_beacon.__version__ import __version__
from warp_beacon.telegram.handlers import Handlers
import warp_beacon.scraper
from warp_beacon.telegram.placeholder_message import PlaceholderMessage
from warp_beacon.storage import Storage
from warp_beacon.uploader import AsyncUploader
from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.jobs.upload_job import UploadJob
from warp_beacon.jobs import Origin
from warp_beacon.jobs.types import JobType
from warp_beacon.telegram.utils import Utils

import logging

class Bot(object):
	storage = Storage()
	uploader = None
	downloader = None
	allow_loop = True
	client = None
	handlers = None
	placeholder = None

	def __init__(self, tg_bot_name: str, tg_token: str, tg_api_id: str, tg_api_hash: str) -> None:
		# Enable logging
		logging.basicConfig(
			format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
		)

		logging.info(f"Starting Warp Beacon version '{__version__}' ...")

		workers_amount = min(32, os.cpu_count() + 4)

		uvloop.install()
		self.client = Client(
			name=tg_bot_name,
			app_version=__version__,
			bot_token=tg_token,
			api_id=tg_api_id,
			api_hash=tg_api_hash,
			workdir='/',
			workers=int(os.environ.get("TG_WORKERS_POOL_SIZE", default=workers_amount))
		)

		this = self
		def __terminator() -> None:
			this.stop()

		stop_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)
		for sig in stop_signals:
			self.client.loop.add_signal_handler(sig, __terminator)

		self.uploader = AsyncUploader(
			storage=self.storage,
			pool_size=int(os.environ.get("UPLOAD_POOL_SIZE", default=workers_amount)),
			loop=self.client.loop
		)
		self.downloader = warp_beacon.scraper.AsyncDownloader(
			workers_count=int(os.environ.get("WORKERS_POOL_SIZE", default=workers_amount)),
			uploader=self.uploader
		)

		self.downloader.start()
		self.uploader.start()

		self.handlers = Handlers(self)

		self.client.add_handler(MessageHandler(self.handlers.start, filters.command("start")))
		self.client.add_handler(MessageHandler(self.handlers.help, filters.command("help")))
		self.client.add_handler(MessageHandler(self.handlers.random, filters.command("random")))
		self.client.add_handler(MessageHandler(self.handlers.handler))

		self.placeholder = PlaceholderMessage(self)

		self.client.run()

	def __del__(self) -> None:
		self.stop()
		logging.info("Warp Beacon terminated.")

	def start(self) -> None:
		self.client.run()

	def stop(self) -> None:
		logging.info("Warp Beacon terminating. This may take a while ...")
		self.downloader.stop_all()
		self.uploader.stop_all()
		#self.client.stop()

	async def send_text(self, chat_id: int, text: str, reply_id: int = None) -> int:
		try:
			message_reply = await self.client.send_message(
				chat_id=chat_id,
				text=text,
				parse_mode=ParseMode.MARKDOWN,
				reply_to_message_id=reply_id
			)
			return message_reply.id
		except Exception as e:
			logging.error("Failed to send text message!")
			logging.exception(e)

		return 0

	def build_tg_args(self, job: UploadJob) -> dict:
		args = {}
		if job.media_type == JobType.VIDEO:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaVideo(media=job.tg_file_id.replace(":video", ''), supports_streaming=True)
				else:
					args["video"] = job.tg_file_id.replace(":video", '')
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaVideo(
						media=job.local_media_path,
						supports_streaming=True,
						width=job.media_info["width"],
						height=job.media_info["height"],
						duration=job.media_info["duration"],
						thumb=job.media_info["thumb"]
					)
				else:
					args["video"] = job.local_media_path
					args["supports_streaming"] = True
					args["width"] = job.media_info["width"]
					args["height"] = job.media_info["height"]
					args["duration"] = job.media_info["duration"]
					args["thumb"] = job.media_info["thumb"]

				args["file_name"] = "downloaded_via_warp_beacon_bot%s" % (os.path.splitext(job.local_media_path)[-1])
		elif job.media_type == JobType.IMAGE:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaPhoto(media=job.tg_file_id.replace(":image", ''))
				else:
					args["photo"] = job.tg_file_id.replace(":image", '')
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaPhoto(
						media=job.local_media_path
					)
				else:
					args["photo"] = job.local_media_path
		elif job.media_type == JobType.AUDIO:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaAudio(
						media=job.tg_file_id.replace(":audio", '')
					)
				else:
					args["audio"] = job.tg_file_id.replace(":audio", '')
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaAudio(
						media=job.local_media_path,
						performer=job.media_info["performer"],
						thumb=job.media_info["thumb"],
						duration=job.media_info["duration"],
						title=job.canonical_name,
					)
				else:
					args["audio"] = job.local_media_path
					args["performer"] = job.media_info["performer"]
					args["thumb"] = job.media_info["thumb"]
					args["duration"] = job.media_info["duration"]
					args["title"] = job.canonical_name
				#args["file_name"] = "%s%s" % (job.canonical_name, os.path.splitext(job.local_media_path)[-1]),
		elif job.media_type == JobType.ANIMATION:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaAnimation(
						media=job.tg_file_id.replace(":animation", '')
					)
				else:
					args["animation"] = job.tg_file_id.replace(":animation", '')
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaAnimation(
						media=job.local_media_path,
						thumb=job.media_info["thumb"],
						duration=job.media_info["duration"],
						width=job.media_info["width"],
						height=job.media_info["height"]
					)
				else:
					args["animation"] = job.local_media_path
					args["width"] = job.media_info["width"]
					args["height"] = job.media_info["height"]
					args["duration"] = job.media_info["duration"]
					args["thumb"] = job.media_info["thumb"]
		elif job.media_type == JobType.COLLECTION:
			if job.tg_file_id:
				args["media"] = []
				for chunk in Utils.chunker(job.tg_file_id.split(','), 10):
					tg_chunk = []
					for i in chunk:
						tg_id, mtype = i.split(':')
						ctype = JobType[mtype.upper()]
						ptr = None
						if ctype == JobType.VIDEO:
							ptr = InputMediaVideo(media=tg_id)
						elif ctype == JobType.IMAGE:
							ptr = InputMediaPhoto(media=tg_id)
						elif ctype == JobType.ANIMATION:
							ptr = InputMediaAnimation(media=tg_id)
						tg_chunk.append(ptr)

					args["media"].append(tg_chunk)
			else:
				mediafs = []
				for chunk in job.media_collection:
					tg_chunk = []
					for j in chunk:
						if j.media_type == JobType.VIDEO:
							vid = InputMediaVideo(
								media=j.local_media_path,
								supports_streaming=True,
								width=j.media_info["width"],
								height=j.media_info["height"],
								duration=int(j.media_info["duration"]),
								thumb=j.media_info["thumb"],
							)
							tg_chunk.append(vid)
						elif j.media_type == JobType.IMAGE:
							photo = InputMediaPhoto(
								media=j.local_media_path
							)
							tg_chunk.append(photo)
					mediafs.append(tg_chunk)
				args["media"] = mediafs

		args["chat_id"] = job.chat_id

		# common args
		if job.placeholder_message_id and job.media_type is not JobType.COLLECTION:
			args["message_id"] = job.placeholder_message_id
		else:
			args["disable_notification"] = True
			args["reply_to_message_id"] = job.message_id

		if os.environ.get("ENABLE_DONATES", None) == "true" and job.media_type is not JobType.COLLECTION:
			args["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton("❤ Donate", url=os.environ.get("DONATE_LINK", "https://pay.cryptocloud.plus/pos/W5BMtNQt5bJFoW2E"))]])

		return args

	async def upload_job(self, job: UploadJob) -> list[str]:
		tg_file_ids = []
		try:
			retry_amount = 0
			max_retries = int(os.environ.get("TG_MAX_RETRIES", default=5))
			while not retry_amount >= max_retries:
				try:
					reply_message = None
					if job.media_type in (JobType.VIDEO, JobType.IMAGE, JobType.AUDIO):
						if job.placeholder_message_id:
							try:
								reply_message = await self.client.edit_message_media(**self.build_tg_args(job))
							except MessageIdInvalid:
								logging.warning("Placeholder message not found. Looks like placeholder message was deleted by administrator.")
								job.placeholder_message_id = None
								continue
						else:
							send_funcs = {
								JobType.VIDEO: self.client.send_video,
								JobType.IMAGE: self.client.send_photo,
								JobType.AUDIO: self.client.send_audio,
								JobType.ANIMATION: self.client.send_animation
							}
							try:
								reply_message = await send_funcs[job.media_type](**self.build_tg_args(job))
							except ValueError as e:
								err_text = str(e)
								if "Expected" in err_text:
									logging.warning("Expectations exceeded reality.")
									logging.warning(err_text)
									expectation, reality = Utils.parse_expected_patronum_error(err_text)
									job_args = self.build_tg_args(job)
									job_args[reality.value.lower()] = job_args.pop(expectation.value.lower())
									reply_message = await send_funcs[reality](**job_args)

						tg_file_id = Utils.extract_file_id(reply_message)
						tg_file_ids.append(tg_file_id)
						job.tg_file_id = tg_file_id
						logging.info("Uploaded media file with type '%s' tg_file_id is '%s'", job.media_type.value, job.tg_file_id)
					elif job.media_type == JobType.COLLECTION:
						col_job_args = self.build_tg_args(job)
						sent_messages = []
						for i, media_chunk in enumerate(col_job_args["media"]):
							messages = await self.client.send_media_group(
								chat_id=job.chat_id,
								reply_to_message_id=job.message_id,
								media=media_chunk,
							)
							sent_messages += messages
							if job.media_collection:
								for j, chunk in enumerate(media_chunk):
									tg_file_id = Utils.extract_file_id(messages[j])
									if tg_file_id:
										job.media_collection[i][j].tg_file_id = tg_file_id
							if i == 0 and job.placeholder_message_id:
								await self.placeholder.remove(job.chat_id, job.placeholder_message_id)
						for msg in sent_messages:
							if msg.video:
								tg_file_ids.append(msg.video.file_id + ':video')
							elif msg.photo:
								tg_file_ids.append(msg.photo.file_id + ':image')
					logging.info("Uploaded to Telegram")
					break
				except MultiMediaTooLong as e:
					logging.error("Failed to upload due telegram limitations :(")
					logging.exception(e)
					await self.placeholder.remove(job.chat_id, job.placeholder_message_id)
					await self.send_text(job.chat_id, e.MESSAGE, job.message_id)
					break
				except (NetworkMigrate, BadRequest) as e:
					logging.error("Network error. Check you Internet connection.")
					logging.exception(e)

					if retry_amount+1 >= max_retries:
						msg = ""
						if e.MESSAGE:
							msg = "Telegram error: %s" % str(e.MESSAGE)
						else:
							msg = "Unfortunately, Telegram limits were exceeded. Your media size is %.2f MB." % job.media_info["filesize"]
						await self.placeholder.remove(job.chat_id, job.placeholder_message_id)
						await self.send_text(job.chat_id, msg, job.message_id)
						break
				retry_amount += 1
		except Exception as e:
			logging.error("Error occurred!")
			logging.exception(e)
		finally:
			job.remove_files()

		return tg_file_ids
