from pyrogram import Client
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import BotCommand

from urlextract import URLExtract

from warp_beacon.storage import Storage
from warp_beacon.telegram.utils import Utils
from warp_beacon.jobs.download_job import DownloadJob
from warp_beacon.jobs.upload_job import UploadJob
from warp_beacon.jobs import Origin
from warp_beacon.jobs.types import JobType

import logging

class Handlers(object):
	storage = None
	bot = None
	url_extractor = URLExtract()

	def __init__(self, bot: "Bot") -> None:
		self.bot = bot
		self.storage = bot.storage

	async def help(self, client: Client, message: Message) -> None:
		"""Send a message when the command /help is issued."""
		await self.bot.send_text(text="Send me a link to remote media", reply_id=message.id, chat_id=message.chat.id)
		#await message.reply_text("<code>test</code>\n<b>bold</b>\n<pre code=\"python\">print('hello')</pre> @BelisariusCawl", parse_mode=ParseMode.HTML)

	async def random(self, client: Client, message: Message) -> None:
		d = self.storage.get_random()
		if not d:
			await message.reply_text("No random content yet. Try to send link first.")
			return
		await self.bot.upload_job(
			UploadJob(
				tg_file_id=d["tg_file_id"],
				chat_id=message.chat.id,
				media_type=JobType[d["media_type"].upper()],
				message_id=message.id,
				chat_type=message.chat.type,
				source_username=Utils.extract_message_author(message)
			)
		)

	async def start(self, client: Client, message: Message) -> None:
		bot_name = await self.bot.client.get_me()
		await self.bot.client.set_bot_commands([
			BotCommand("start", "Start bot"),
			BotCommand("help", "Show help message"),
			BotCommand("random", "Get random media")
		])
		await message.reply_text(
			parse_mode=ParseMode.HTML,
			text=f"Welcome to @{bot_name.username}!\n"
			"Send link to external social network with content and I'll reply to it.\n"
			"Currently supported: Instagram, YouTube Shorts and YouTube Music."
		)

	async def handler(self, client: Client, message: Message) -> None:
		if message is None:
			return
		message_text = Utils.extract_message_text(message)
		if not message_text:
			return
		chat = message.chat
		effective_message_id = message.id
		urls = self.url_extractor.find_urls(message_text)

		reply_text = "Wut?"
		if not urls:
			reply_text = "Your message should contains URLs"
		else:
			for url in urls:
				origin = Utils.extract_origin(url)
				if origin is Origin.INSTAGRAM:
					url = Utils.resolve_ig_share_link(url)
				if origin is Origin.YOUTU_BE:
					url = Utils.extract_youtu_be_link(url)
					if not url:
						raise ValueError("Failed to extract youtu.be link")
					origin = Origin.YOUTUBE
				if origin is Origin.UNKNOWN:
					logging.info("Only Instagram, YouTube Shorts and YouTube Music are now supported. Skipping.")
					continue
				entities, tg_file_ids = [], []
				uniq_id = Storage.compute_uniq(url)
				try:
					entities = self.storage.db_lookup_id(uniq_id)
				except Exception as e:
					logging.error("Failed to search link in DB!")
					logging.exception(e)
				if entities:
					tg_file_ids = [i["tg_file_id"] for i in entities]
					logging.info("URL '%s' is found in DB. Sending with tg_file_ids = '%s'", url, str(tg_file_ids))
					ent_len = len(entities)
					if ent_len > 1:
						await self.bot.upload_job(
							UploadJob(
								url=url,
								tg_file_id=",".join(tg_file_ids),
								message_id=effective_message_id,
								media_type=JobType.COLLECTION,
								chat_id=chat.id,
								chat_type=message.chat.type,
								source_username=Utils.extract_message_author(message)
							)
						)
					elif ent_len:
						media_type = JobType[entities[0]["media_type"].upper()]
						canonical_name = entities[0]["canonical_name"]
						await self.bot.upload_job(
							UploadJob(
								url=url,
								tg_file_id=tg_file_ids.pop(),
								message_id=effective_message_id,
								media_type=media_type,
								chat_id=chat.id,
								chat_type=message.chat.type,
								source_username=Utils.extract_message_author(message),
								canonical_name=canonical_name
							)
						)
				else:
					async def upload_wrapper(job: UploadJob) -> None:
						try:
							if job.job_failed and job.job_failed_msg:
								if job.placeholder_message_id:
									await self.bot.placeholder.remove(chat.id, job.placeholder_message_id)
								return await self.bot.send_text(chat_id=chat.id, text=job.job_failed_msg, reply_id=job.message_id)
							if job.job_warning and job.job_warning_msg:
								return await self.bot.placeholder.update_text(chat.id, job.placeholder_message_id, job.job_warning_msg)
							tg_file_ids = await self.bot.upload_job(job)
							if tg_file_ids:
								if job.media_type == JobType.COLLECTION and job.save_items:
									for chunk in job.media_collection:
										for i in chunk:
											self.storage.add_media(
												tg_file_ids=[i.tg_file_id],
												media_url=i.effective_url,
												media_type=i.media_type.value,
												origin=job.job_origin.value,
												canonical_name=job.canonical_name
											)
								else:
									self.storage.add_media(
										tg_file_ids=[','.join(tg_file_ids)],
										media_url=job.url,
										media_type=job.media_type.value,
										origin=job.job_origin.value,
										canonical_name=job.canonical_name
									)
						except Exception as e:
							logging.error("Exception occurred while performing upload callback!")
							logging.exception(e)

					try:
						# create placeholder message for long download
						placeholder_message_id = await self.bot.placeholder.create(
							chat_id=chat.id,
							reply_id=effective_message_id
						)

						if not placeholder_message_id:
							await self.bot.send_text(
								chat_id=chat.id,
								reply_id=effective_message_id,
								text="Failed to create message placeholder. Please check your bot Internet connection.")
							return

						self.bot.uploader.add_callback(
							placeholder_message_id,
							upload_wrapper
						)

						self.bot.downloader.queue_task(DownloadJob.build(
							url=url,
							placeholder_message_id=placeholder_message_id,
							message_id=effective_message_id,
							chat_id=chat.id,
							in_process=self.bot.uploader.is_inprocess(uniq_id),
							uniq_id=uniq_id,
							job_origin=origin,
							source_username=Utils.extract_message_author(message),
							chat_type=chat.type
						))
						self.bot.uploader.set_inprocess(uniq_id)
					except Exception as e:
						logging.error("Failed to schedule download task!")
						logging.exception(e)

		if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP) and not urls:
			await self.bot.send_text(text=reply_text, reply_id=effective_message_id, chat_id=chat.id)

	async def simple_button_handler(self, client: Client, query: CallbackQuery) -> None:
		await client.answer_callback_query(
			callback_query_id=query.id,
			text="Please wait, bot will try to download media with obtained credentials.\nIf authorization is not successful, the operation will be repeated.",
			show_alert=True
		)
		self.bot.downloader.auth_event.set()
		self.bot.downloader.auth_event.clear()