#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from typing import Optional, Callable
import signal
import asyncio
import logging

from urlextract import URLExtract

import scrapler
from storage import Storage
from uploader import AsyncUploader
from jobs.download_job import DownloadJob, UploadJob

from telegram import ForceReply, Update, Chat, error
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


# Enable logging
logging.basicConfig(
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

storage = Storage()
uploader = None
downloader = None

# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Send a message when the command /start is issued."""
	user = update.effective_user
	await update.message.reply_html(
		rf"Hi {user.mention_html()}!",
		reply_markup=ForceReply(selective=True),
	)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Send a message when the command /help is issued."""
	await update.message.reply_text("Send me a link to remote media")

async def random(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	d = storage.get_random()
	if not d:
		await update.message.reply_text("No random content yet.")
		return
	await send_without_upload(update, context, d["tg_file_id"], update.message.message_id)

async def send_text(update: Update, context: ContextTypes.DEFAULT_TYPE, reply_id: int, text: str) -> None:
	try:
		await update.message.reply_text(
			text, 
			reply_to_message_id=reply_id
		)
	except Exception as e:
		logging.error("Failed to send text message!")
		logging.exception(e)

async def send_without_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, tg_file_id: str, effective_message_id: int) -> None:
	try:
		timeout = int(os.environ.get("TG_WRITE_TIMEOUT", default=120))
		await update.message.reply_video(
			video=tg_file_id, 
			reply_to_message_id=effective_message_id, 
			disable_notification=True,
			write_timeout=timeout,
			read_timeout=timeout,
			connect_timeout=timeout)
	except Exception as e:
		logging.error("Failed to send video with tg_file_id = '%s'!", tg_file_id)
		logging.exception(e)

async def send_video(update: Update, 
	context: ContextTypes.DEFAULT_TYPE,
	local_media_path: str, 
	media_info: Optional[dict],
	url: str, 
	uniq_id: str,
	tg_file_id: str=None) -> bool:
	
	effective_message_id = None
	timeout = int(os.environ.get("TG_WRITE_TIMEOUT", default=120))
	try:
		effective_message_id = update.message.message_id

		if tg_file_id:
			return await send_without_upload(update, context, tg_file_id, effective_message_id)

		message = await update.message.reply_video(
			video=open(local_media_path, 'rb'), 
			reply_to_message_id=effective_message_id, 
			supports_streaming=True,
			disable_notification=True,
			duration=media_info["duration"],
			width=media_info["width"],
			height=media_info["height"],
			thumbnail=media_info["thumb"],
			write_timeout=timeout,
			read_timeout=timeout,
			connect_timeout=timeout)
		storage.add_media(tg_file_id=message.video.file_id, media_url=url, origin="instagram")
		logging.info("File '%s' is uploaded successfully, tg_file_id is '%s'", local_media_path, message.video.file_id)
	except error.TimedOut as e:
		logging.error("TG timeout error!")
		logging.exception(e)
		await send_text(
			update, 
			context, 
			effective_message_id,
			"Telegram timeout error occurred! Your configuration timeout value is `%d`" % timeout
		)
	except error.NetworkError as e:
		logging.error("Failed to upload due telegram limits :(")
		logging.exception(e)
		await send_text(
			update, 
			context, 
			effective_message_id,
			"Unfortunately, Telegram limits were exceeded. Your video size is %.2f MB." % media_info["filesize"]
		)
	except Exception as e:
		logging.error("Error occurred!")
		logging.exception(e)
	finally:
		if os.path.exists(local_media_path):
			os.unlink(local_media_path)

	return True

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.message is None:
		return
	chat = update.effective_chat
	effective_message_id = update.message.message_id
	extractor = URLExtract()
	urls = extractor.find_urls(update.message.text_html)

	reply_text = "Wut?"
	if not urls:
		reply_text = "Your message should contains URLs"
	else:
		for url in urls:
			if "instagram.com" not in url:
				logging.info("Only instagram.com is now supported. Skipping.")
				continue
			doc = None
			tg_file_id = ""
			uniq_id = Storage.compute_uniq(url)
			try:
				doc = storage.db_lookup_id(uniq_id)
			except Exception as e:
				logging.error("Failed to search link in DB!")
				logging.exception(e)
			if doc:
				tg_file_id = doc["tg_file_id"]
				logging.info("URL '%s' is found in DB. Sending with tg_file_id = '%s'", url, tg_file_id)
				await send_without_upload(update, context, tg_file_id, effective_message_id)
			else:
				async def send_video_wrapper(job: UploadJob) -> None:
					ret = await send_video(update, context, job.local_media_path, job.media_info, job.url, job.uniq_id, job.tg_file_id)
					uploader.process_done(job.uniq_id)
					return ret

				uploader.add_callback(effective_message_id, send_video_wrapper, update, context)

				logging.info("Downloading URL '%s' from instagram ...", url)
				try:
					downloader.queue_task(DownloadJob.build(url=url, 
						message_id=effective_message_id, 
						in_process=uploader.is_inprocess(uniq_id), 
						uniq_id=uniq_id
					))
					uploader.set_inprocess(uniq_id)
				except Exception as e:
					logging.error("Failed to schedule download task!")
					logging.exception(e)

	if chat.type not in (Chat.GROUP, Chat.SUPERGROUP) and not urls:
		await update.message.reply_text(reply_text, reply_to_message_id=effective_message_id)

@staticmethod
def _raise_system_exit() -> None:
	raise SystemExit

def main() -> None:
	"""Start the bot."""
	try:
		global uploader, downloader

		loop = asyncio.get_event_loop()
		stop_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)
		for sig in stop_signals or []:
			loop.add_signal_handler(sig, _raise_system_exit)
		loop.add_signal_handler(sig, _raise_system_exit)
		
		uploader = AsyncUploader(
			storage=storage,
			pool_size=int(os.environ.get("UPLOAD_POOL_SIZE", default=scrapler.CONST_CPU_COUNT)),
			loop=loop
		)
		downloader = scrapler.AsyncDownloader(
			workers_count=int(os.environ.get("WORKERS_POOL_SIZE", default=scrapler.CONST_CPU_COUNT)),
			uploader=uploader
		)
		downloader.start()
		uploader.start()

		# Create the Application and pass it your bot's token.
		application = Application.builder().token(os.environ.get("TG_TOKEN", default=None)).concurrent_updates(True).build()

		# on different commands - answer in Telegram
		application.add_handler(CommandHandler("start", start))
		application.add_handler(CommandHandler("random", random))
		application.add_handler(CommandHandler("help", help_command))

		# on non command i.e message - echo the message on Telegram
		application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

		try:
			loop.run_until_complete(application.initialize())
			if application.post_init:
				loop.run_until_complete(application.post_init(application))
			loop.run_until_complete(application.updater.start_polling())
			loop.run_until_complete(application.start())
			loop.run_forever()
		except (KeyboardInterrupt, SystemExit):
			logging.debug("Application received stop signal. Shutting down.")
		finally:
			try:
				if application.updater.running:  # type: ignore[union-attr]
					loop.run_until_complete(application.updater.stop())  # type: ignore[union-attr]
				if application.running:
					loop.run_until_complete(application.stop())
				if application.post_stop:
					loop.run_until_complete(application.post_stop(application))
				loop.run_until_complete(application.shutdown())
				if application.post_shutdown:
					loop.run_until_complete(application.post_shutdown(application))
			finally:
				loop.close()
				downloader.stop_all()
				uploader.stop_all()
	except Exception as e:
		logging.exception(e)

if __name__ == "__main__":
	main()