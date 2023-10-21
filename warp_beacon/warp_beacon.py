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
	await upload_job(update, context, UploadJob(tg_file_id=d["tg_file_id"], message_id=update.message.message_id))

async def send_text(update: Update, context: ContextTypes.DEFAULT_TYPE, reply_id: int, text: str) -> None:
	try:
		await update.message.reply_text(
			text, 
			reply_to_message_id=reply_id
		)
	except Exception as e:
		logging.error("Failed to send text message!")
		logging.exception(e)

def build_tg_args(job: UploadJob) -> dict:
	args = {}
	timeout = int(os.environ.get("TG_WRITE_TIMEOUT", default=120))
	if job.media_type == "video":
		if job.tg_file_id:
			args["video"] = job.tg_file_id
		else:
			args["video"] = open(job.local_media_path, 'rb')
			args["supports_streaming"] = True
			args["duration"] = job.media_info["duration"]
			args["width"] = job.media_info["width"]
			args["height"] = job.media_info["height"]
			args["thumbnail"] = job.media_info["thumb"]
	elif job.media_type == "photo":
		if job.tg_file_id:
			args["photo"] = job.tg_file_id
		else:
			args["photo"] = open(job.local_media_path, 'rb')

	# common args
	args["disable_notification"] = True
	args["write_timeout"] = timeout
	args["read_timeout"] = timeout
	args["connect_timeout"] = timeout
	args["reply_to_message_id"] = job.message_id

	return args

async def upload_job(update: Update, context: ContextTypes.DEFAULT_TYPE, job: UploadJob) -> bool:
	timeout = int(os.environ.get("TG_WRITE_TIMEOUT", default=120))
	try:
		if job.media_type == "video":
			await update.message.reply_video(**build_tg_args(job))
		elif job.media_type == "image":
			await update.message.reply_photo(**build_tg_args(job))
			
		return True
	except error.TimedOut as e:
		logging.error("TG timeout error!")
		logging.exception(e)
		await send_text(
			update, 
			context, 
			job.message_id,
			"Telegram timeout error occurred! Your configuration timeout value is `%d`" % timeout
		)
	except error.NetworkError as e:
		logging.error("Failed to upload due telegram limits :(")
		logging.exception(e)
		await send_text(
			update, 
			context, 
			job.message_id,
			"Unfortunately, Telegram limits were exceeded. Your video size is %.2f MB." % job.media_info["filesize"]
		)
	except Exception as e:
		logging.error("Error occurred!")
		logging.exception(e)
	finally:
		if os.path.exists(job.local_media_path):
			os.unlink(job.local_media_path)

	return False

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
				await upload_job(update, context, UploadJob(tg_file_id=tg_file_id, message_id=effective_message_id, media_type=doc["media_type"]))
			else:
				async def upload_wrapper(job: UploadJob) -> None:
					await upload_job(update, context, job)
					uploader.process_done(job.uniq_id)
					storage.add_media(tg_file_id=job.tg_file_id, media_url=job.url, media_type=job.media_type, origin="instagram")

				uploader.add_callback(effective_message_id, upload_wrapper, update, context)

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