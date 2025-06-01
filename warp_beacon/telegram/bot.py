import os
import signal
import asyncio
from typing import Optional, Union

import logging
import html
import uvloop

from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatType
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import InputMediaAudio, InputMediaPhoto, InputMediaVideo, InputMediaAnimation, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import NetworkMigrate, BadRequest, MultiMediaTooLong, MessageIdInvalid

import warp_beacon
from warp_beacon.__version__ import __version__
from warp_beacon.telegram.handlers import Handlers
from warp_beacon.telegram.placeholder_message import PlaceholderMessage
from warp_beacon.storage.mongo import DBClient
from warp_beacon.storage import Storage
from warp_beacon.uploader import AsyncUploader
from warp_beacon.jobs.upload_job import UploadJob
from warp_beacon.jobs.types import JobType
from warp_beacon.jobs import Origin
from warp_beacon.telegram.utils import Utils
from warp_beacon.telegram.caption_shortener import CaptionShortner
from warp_beacon.scheduler.scheduler import IGScheduler
from warp_beacon.telegram.edit_message import EditMessage
from warp_beacon.telegram.download_status import DownloadStatus

class Bot(object):
	should_exit = None
	storage = None
	uploader = None
	downloader = None
	allow_loop = True
	client = None
	handlers = None
	placeholder = None
	scheduler = None
	me = None
	edit_message = None
	download_status = None

	def __init__(self, tg_bot_name: str, tg_token: str, tg_api_id: str, tg_api_hash: str) -> None:
		# Enable logging
		logging.basicConfig(
			format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
			level=logging.INFO
		)

		logging.getLogger("pyrogram").setLevel(logging.ERROR)
		logging.info("Starting Warp Beacon version '%s' ...", __version__)
		self.storage = Storage(DBClient())
		self.should_exit = asyncio.Event()
		workers_amount = min(32, os.cpu_count() + 4)

		uvloop.install()
		self.client = Client(
			name=tg_bot_name,
			app_version=__version__,
			bot_token=tg_token,
			api_id=tg_api_id,
			api_hash=tg_api_hash,
			workdir='/var/warp_beacon',
			workers=int(os.environ.get("TG_WORKERS_POOL_SIZE", default=workers_amount)),
			ipv6=os.environ.get("TG_IPV6", default="false").lower() in ("1", "true", "yes")
		)

		self.editor = EditMessage(self.client)

		self.uploader = AsyncUploader(
			storage=self.storage,
			admin_message_callback=self.send_text_to_admin,
			request_yt_auth_callback=self.request_yt_auth,
			pool_size=int(os.environ.get("UPLOAD_POOL_SIZE", default=workers_amount)),
			loop=self.client.loop
		)
		self.download_status = DownloadStatus(self.client)
		self.downloader = warp_beacon.scraper.AsyncDownloader(
			workers_count=int(os.environ.get("WORKERS_POOL_SIZE", default=workers_amount)),
			uploader=self.uploader,
			pipe_connection=self.download_status.child_conn
		)

		self.scheduler = IGScheduler(self.downloader)
		self.handlers = Handlers(self)

		self.client.add_handler(MessageHandler(self.handlers.start, filters.command("start")))
		self.client.add_handler(MessageHandler(self.handlers.help, filters.command("help")))
		self.client.add_handler(MessageHandler(self.handlers.random, filters.command("random")))
		self.client.add_handler(MessageHandler(self.handlers.handler))
		#TODO refactor to callback router
		self.client.add_handler(CallbackQueryHandler(self.handlers.simple_button_handler, filters=filters.create(lambda _, __, q: not q.data.startswith("read_more:"))))
		self.client.add_handler(CallbackQueryHandler(self.handlers.read_more_handler, filters=filters.create(lambda _, __, q: q.data.startswith("read_more:"))))

		self.placeholder = PlaceholderMessage(self)

	def __del__(self) -> None:
		self.stop()

	def start(self) -> None:
		self.client.run(self.run())

	async def run(self) -> None:
		loop = asyncio.get_running_loop()
		for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
			loop.add_signal_handler(sig, self.should_exit.set)
		async with self.client:
			self.me = await self.client.get_me()
			self.client.me = self.me
			if self.me.is_premium:
				os.environ["TG_PREMIUM"] = "true"
			self.downloader.start()
			self.uploader.start()
			loop.add_reader(self.download_status.status_pipe.fileno(), self.download_status.on_status)
			self.scheduler.start()
			logging.info("Warp Beacon version '%s' started", __version__)
			await self.should_exit.wait()

		self.stop()
		logging.info("Warp Beacon version '%s' terminated.", __version__)

	def stop(self) -> None:
		logging.info("Warp Beacon is terminating. This may take a while ...")
		self.scheduler.stop()
		self.downloader.stop_all()
		self.uploader.stop_all()
		if self.client and self.client.is_initialized and self.client.is_connected:
			asyncio.run_coroutine_threadsafe(self.client.stop(), self.client.loop)

	async def send_text(self, chat_id: int, text: str, reply_id: int = None) -> int:
		try:
			message_reply = await self.client.send_message(
				chat_id=chat_id,
				text=text,
				parse_mode=ParseMode.HTML,
				reply_to_message_id=reply_id
			)
			return message_reply.id
		except Exception as e:
			logging.error("Failed to send text message!")
			logging.exception(e)

		return 0

	async def request_yt_auth(self) -> None:
		from warp_beacon.yt_auth import YtAuth
		acc_index, acc = self.downloader.acc_selector.get_current_for_module(Origin.YOUTUBE)
		yt_auth = YtAuth(account_index=acc_index)
		data = yt_auth.fetch_token()
		if all(data.values()):
			if yt_auth.store_device_code(data["device_code"]):
				reply_markup = InlineKeyboardMarkup(
					[
						[
							InlineKeyboardButton("✅ Done", callback_data=f"confirm_yt_auth:{acc_index}")
						]
					]
				)
				await self.send_text_to_admin(
					f"Please open {data['verification_url']} and input code <code>{data['user_code']}</code>.\n\n"
					"Please authorize with a Google account with verified age.\n"
					"This will allow you to avoid error the <b>AgeRestrictedError</b> when accessing some content.",
					account_admins=acc.get("account_admins", None),
					reply_markup=reply_markup
				)
		else:
			logging.error("Wrong YT auth dataset: '%s'", str(data))

	async def send_text_to_admin(self, text: str, account_admins: str = None, reply_markup: Optional[Union[InlineKeyboardMarkup]] = None) -> list[int]:
		try:
			admins = None
			if account_admins:
				admins = account_admins
			if not admins:
				admins = os.environ.get("TG_BOT_ADMINS_USERNAMES", None)
			if not admins:
				raise ValueError("Configuration value `TG_BOT_ADMIN_USERNAME` is empty!")
			
			msg_ids = []
			admins_array = admins.split(',')
			for adm in admins_array:
				adm = adm.strip()
				msg_opts = {"chat_id": adm, "text": text, "parse_mode": ParseMode.HTML}
				if reply_markup:
					msg_opts["reply_markup"] = reply_markup
				message_reply = await self.client.send_message(**msg_opts)
				msg_ids.append(message_reply.id)
			return msg_ids
		except Exception as e:
			logging.error("Failed to send text message to admin!")
			logging.exception(e)

		return []

	def build_signature_caption(self, job: UploadJob, override_canonical_name: str = None) -> str:
		caption = ""
		is_group = job.chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)
		is_youtube = job.job_origin in (Origin.YOUTUBE, Origin.YT_SHORTS)
		effective_canonical_name = override_canonical_name or job.canonical_name
		if effective_canonical_name:
			if is_group and not is_youtube and CaptionShortner.need_short(effective_canonical_name):
				caption = f"{html.escape(CaptionShortner.smart_truncate_html(effective_canonical_name))} ..."
				job.short_text = True
			elif is_group:
				# short enough
				caption = html.escape(effective_canonical_name)
			# Captions only for YouTube in groups; empty otherwise.
			# Might be too long for Telegram, so we skip them.
			if is_youtube and is_group:
				caption = f"<b>{html.escape(effective_canonical_name)}</b>"
		if is_group:
			if effective_canonical_name:
				caption += "\n—\n"
			if job.message_leftover:
				caption += job.message_leftover
				caption += "\n—\n"
			if job.source_username:
				if job.source_username.startswith("<a href="):
					caption += f"Requested by <b>{job.source_username}</b>"
				else:
					caption += f"Requested by <b>@{job.source_username}</b>"
			if job.source_username and job.url:
				caption += " | "
			if job.url:
				caption += f'<a href="{job.url}">source link</a>'

		return caption

	def build_tg_args(self, job: UploadJob) -> dict:
		args = {}
		if job.media_type == JobType.VIDEO:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaVideo(
						media=job.tg_file_id.replace(":video", ''),
						supports_streaming=True,
						caption=self.build_signature_caption(job)
					)
				else:
					args["video"] = job.tg_file_id.replace(":video", '')
					args["caption"] = self.build_signature_caption(job)
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaVideo(
						media=job.local_media_path,
						supports_streaming=True,
						width=job.media_info["width"],
						height=job.media_info["height"],
						duration=round(job.media_info["duration"]),
						thumb=job.media_info["thumb"],
						caption=self.build_signature_caption(job)
					)
				else:
					args["video"] = job.local_media_path
					args["supports_streaming"] = True
					args["width"] = job.media_info["width"]
					args["height"] = job.media_info["height"]
					args["duration"] = round(job.media_info["duration"])
					args["thumb"] = job.media_info["thumb"]
					args["caption"] = self.build_signature_caption(job)

				args["file_name"] = os.path.basename(job.local_media_path)
		elif job.media_type == JobType.IMAGE:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaPhoto(
						media=job.tg_file_id.replace(":image", ''),
						caption=self.build_signature_caption(job)
					)
				else:
					args["photo"] = job.tg_file_id.replace(":image", '')
					args["caption"] = self.build_signature_caption(job)
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaPhoto(
						media=job.local_media_path,
						caption=self.build_signature_caption(job)
					)
				else:
					args["photo"] = job.local_media_path
					args["caption"] = self.build_signature_caption(job)

				args["file_name"] = os.path.basename(job.local_media_path)
		elif job.media_type == JobType.AUDIO:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaAudio(
						media=job.tg_file_id.replace(":audio", ''),
						caption=self.build_signature_caption(job)
					)
				else:
					args["audio"] = job.tg_file_id.replace(":audio", '')
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaAudio(
						media=job.local_media_path,
						performer=job.media_info["performer"],
						thumb=job.media_info["thumb"],
						duration=round(job.media_info["duration"]),
						title=job.canonical_name,
						caption=self.build_signature_caption(job)
					)
				else:
					args["audio"] = job.local_media_path
					args["performer"] = job.media_info["performer"]
					args["thumb"] = job.media_info["thumb"]
					args["duration"] = round(job.media_info["duration"])
					args["title"] = job.canonical_name
					args["caption"] = self.build_signature_caption(job)

				args["file_name"] = os.path.basename(job.local_media_path)
		elif job.media_type == JobType.ANIMATION:
			if job.tg_file_id:
				if job.placeholder_message_id:
					args["media"] = InputMediaAnimation(
						media=job.tg_file_id.replace(":animation", ''),
						caption=self.build_signature_caption(job)
					)
				else:
					args["animation"] = job.tg_file_id.replace(":animation", '')
					args["caption"] = self.build_signature_caption(job)
			else:
				if job.placeholder_message_id:
					args["media"] = InputMediaAnimation(
						media=job.local_media_path,
						thumb=job.media_info["thumb"],
						duration=round(job.media_info["duration"]),
						width=job.media_info["width"],
						height=job.media_info["height"],
						caption=self.build_signature_caption(job)
					)
				else:
					args["animation"] = job.local_media_path
					args["width"] = job.media_info["width"]
					args["height"] = job.media_info["height"]
					args["duration"] = round(job.media_info["duration"])
					args["thumb"] = job.media_info["thumb"]
					args["caption"] = self.build_signature_caption(job)

				args["file_name"] = os.path.basename(job.local_media_path)
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
							ptr = InputMediaVideo(media=tg_id, caption=self.build_signature_caption(job))
						elif ctype == JobType.IMAGE:
							ptr = InputMediaPhoto(media=tg_id, caption=self.build_signature_caption(job))
						elif ctype == JobType.ANIMATION:
							ptr = InputMediaAnimation(media=tg_id, caption=self.build_signature_caption(job))
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
								duration=round(j.media_info["duration"]),
								thumb=j.media_info["thumb"],
								caption=self.build_signature_caption(job, j.canonical_name)
							)
							tg_chunk.append(vid)
						elif j.media_type == JobType.IMAGE:
							photo = InputMediaPhoto(
								media=j.local_media_path,
								caption=self.build_signature_caption(job, j.canonical_name)
							)
							tg_chunk.append(photo)
						elif j.media_type == JobType.ANIMATION:
							anim = InputMediaAnimation(
								media=j.local_media_path,
								thumb=j.media_info["thumb"],
								caption=self.build_signature_caption(job, j.canonical_name),
								width=j.media_info["width"],
								height=j.media_info["height"],
								duration=round(j.media_info["duration"])
							)
							tg_chunk.append(anim)
					mediafs.append(tg_chunk)
				args["media"] = mediafs

		args["chat_id"] = job.chat_id

		# common args
		if job.placeholder_message_id and job.media_type is not JobType.COLLECTION:
			args["message_id"] = job.placeholder_message_id
		else:
			args["disable_notification"] = True
			args["reply_to_message_id"] = job.message_id

		if job.media_type is not JobType.COLLECTION:
			render_donates = os.environ.get("ENABLE_DONATES", None) == "true"
			keyboard_buttons = [[]]
			# short_text is True only for groups
			if job.short_text:
				keyboard_buttons[0].append(InlineKeyboardButton("📖 Read more", callback_data=f"read_more:{job.job_origin.value}:{job.uniq_id}"))
			if render_donates:
				keyboard_buttons[0].append(InlineKeyboardButton("❤ Donate", url=os.environ.get("DONATE_LINK", "https://pay.cryptocloud.plus/pos/W5BMtNQt5bJFoW2E")))

			if keyboard_buttons[0]:  #job.short_text or render_donates:
				args["reply_markup"] = InlineKeyboardMarkup(keyboard_buttons)

		return args

	async def upload_job(self, job: UploadJob) -> list[str]:
		tg_file_ids = []
		try:
			retry_amount = 0
			max_retries = int(os.environ.get("TG_MAX_RETRIES", default=5))
			while not retry_amount >= max_retries:
				try:
					reply_message = None
					if job.media_type in (JobType.VIDEO, JobType.IMAGE, JobType.AUDIO, JobType.ANIMATION):
						if job.media_type in (JobType.VIDEO, JobType.AUDIO):
							await Utils.ensure_me_loaded(self.client)
						if job.placeholder_message_id:
							try:
								reply_message = await self.editor.edit(**self.build_tg_args(job))
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
						snd_grp_options = {"chat_id": job.chat_id, "reply_to_message_id": job.message_id}
						for i, media_chunk in enumerate(col_job_args["media"]):
							snd_grp_options["media"] = media_chunk
							messages = await self.client.send_media_group(**snd_grp_options)
							sent_messages += messages
							if job.media_collection:
								for j, _ in enumerate(media_chunk):
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
					if job.chat_type not in (ChatType.GROUP, ChatType.SUPERGROUP):
						if job.canonical_name:
							await self.send_text(chat_id=job.user_id, text=job.canonical_name)
					break
				except MultiMediaTooLong as e:
					logging.error("Failed to upload due telegram limitations :(")
					logging.exception(e)
					await self.placeholder.remove(job.chat_id, job.placeholder_message_id)
					await self.send_text(job.chat_id, e.MESSAGE, job.message_id)
					break
				except (NetworkMigrate, BadRequest, AttributeError) as e:
					import traceback
					logging.error("Network error. Check you Internet connection.")
					logging.exception(e)

					if retry_amount+1 >= max_retries:
						msg = ""
						if hasattr(e, "MESSAGE") and e.MESSAGE:
							msg = f"Telegram error: {str(e.MESSAGE)}"
						else:
							msg = (f"Unknown Telegram error. Known information:\n<pre language=\"python\">\n{traceback.format_exc().strip()}</pre>"
									"\nPlease <a href=\"https://github.com/sb0y/warp_beacon/issues\">create issue</a> with this info and service logs.")
						await self.placeholder.remove(job.chat_id, job.placeholder_message_id)
						await self.send_text(job.chat_id, msg, job.message_id)
						break
				retry_amount += 1
		except Exception as e:
			logging.error("Error occurred!")
			logging.exception(e)
		finally:
			job.remove_files()

		if job.chat_type in (ChatType.GROUP, ChatType.SUPERGROUP):
			try:
				await self.client.delete_messages(job.chat_id, (job.message_id,))
			except Exception as e:
				logging.warning("Failed to delete source message. Check bot permissions in Telegram chat settings.")
				logging.exception(e)

		return tg_file_ids