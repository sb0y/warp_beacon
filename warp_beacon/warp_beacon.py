#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import signal
import asyncio
import logging

from urlextract import URLExtract

from telegram import ForceReply, Update, Chat, error, InputMediaVideo, InputMediaPhoto
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import warp_beacon.scrapler
from warp_beacon.storage import Storage
from warp_beacon.uploader import AsyncUploader
from warp_beacon.jobs.download_job import DownloadJob, UploadJob

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
	await upload_job(update, context, UploadJob(tg_file_id=d["tg_file_id"], media_type=d["media_type"], message_id=update.message.message_id))

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
			args["video"] = job.tg_file_id.replace(":video", '')
		else:
			args["video"] = open(job.local_media_path, 'rb')
			args["supports_streaming"] = True
			args["duration"] = int(job.media_info["duration"])
			args["width"] = job.media_info["width"]
			args["height"] = job.media_info["height"]
			args["thumbnail"] = job.media_info["thumb"]
	elif job.media_type == "image":
		if job.tg_file_id:
			args["photo"] = job.tg_file_id.replace(":image", '')
		else:
			args["photo"] = open(job.local_media_path, 'rb')
	elif job.media_type == "collection":
		if job.tg_file_id:
			args["media"] = []
			for i in job.tg_file_id.split(','):
				tg_id, mtype = i.split(':')
				ptr = None
				if mtype == "video":
					ptr = InputMediaVideo(media=tg_id)
				elif mtype == "image":
					ptr = InputMediaPhoto(media=tg_id)
				args["media"].append(ptr)
		else:
			mediafs = []
			for j in job.media_collection:
				if j.media_type == "video":
					vid = InputMediaVideo(
						media=open(j.local_media_path, 'rb'),
						supports_streaming=True,
						width=j.media_info["width"],
						height=j.media_info["height"],
						duration=int(j.media_info["duration"]),
						thumbnail=j.media_info["thumb"]
					)
					mediafs.append(vid)
				elif j.media_type == "image":
					photo = InputMediaPhoto(
						media=open(j.local_media_path, 'rb')
					)
					mediafs.append(photo)
			args["media"] = mediafs

	# common args
	args["disable_notification"] = True
	args["write_timeout"] = timeout
	args["read_timeout"] = timeout
	args["connect_timeout"] = timeout
	args["reply_to_message_id"] = job.message_id

	return args

async def upload_job(update: Update, context: ContextTypes.DEFAULT_TYPE, job: UploadJob) -> list[str]:
	timeout = int(os.environ.get("TG_WRITE_TIMEOUT", default=120))
	tg_file_ids = []
	try:
		retry_amount = 0
		max_retries = int(os.environ.get("TG_MAX_RETRIES", default=5))
		while not retry_amount >= max_retries:
			try:
				if job.media_type == "video":
					message = await update.message.reply_video(**build_tg_args(job))
					tg_file_ids.append(message.video.file_id)
					job.tg_file_id = message.video.file_id
				elif job.media_type == "image":
					message = await update.message.reply_photo(**build_tg_args(job))
					if message.photo:
						tg_file_ids.append(message.photo[-1].file_id)
						job.tg_file_id = message.photo[-1].file_id
				elif job.media_type == "collection":
					sent_messages = await update.message.reply_media_group(**build_tg_args(job))
					for i, msg in enumerate(sent_messages):
						if msg.video:
							tg_file_ids.append(msg.video.file_id + ':video')
							if job.media_collection:
								job.media_collection[i].tg_file_id = msg.video.file_id + ':video'
						elif msg.photo:
							tg_file_ids.append(msg.photo[-1].file_id + ':image')
							if job.media_collection:
								job.media_collection[i].tg_file_id = msg.photo[-1].file_id + ':image'
				logging.info("Uploaded to Telegram")
				break
			except error.TimedOut as e:
				logging.error("TG timeout error!")
				logging.exception(e)
				await send_text(
					update,
					context,
					job.message_id,
					"Telegram timeout error occurred! Your configuration timeout value is `%d`" % timeout
				)
				break
			except error.NetworkError as e:
				logging.error("Failed to upload due telegram limits :(")
				logging.exception(e)
				if not "Request Entity Too Large" in e.message:
					logging.info("TG upload will be retried. Configuration `TG_MAX_RETRIES` values is %d.", max_retries)
				
				if "Message to reply not found" in e.message:
					logging.warning("No message to reply found. Looks like original message was deleted by author.")
					job.message_id = None
					continue

				if retry_amount+1 >= max_retries or "Request Entity Too Large" in e.message:
					msg = ""
					if e.message:
						msg = "Telegram error: %s" % str(e.message)
					else:
						msg = "Unfortunately, Telegram limits were exceeded. Your video size is %.2f MB." % job.media_info["filesize"]
					await send_text(
						update,
						context,
						job.message_id,
						msg
					)
					break
			retry_amount += 1
	except Exception as e:
		logging.error("Error occurred!")
		logging.exception(e)
	finally:
		if job.media_type == "collection":
			for j in job.media_collection:
				if os.path.exists(j.local_media_path):
					os.unlink(j.local_media_path)
		else:
			if os.path.exists(job.local_media_path):
				os.unlink(job.local_media_path)

	return tg_file_ids

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
			entities, tg_file_ids = [], []
			uniq_id = Storage.compute_uniq(url)
			try:
				entities = storage.db_lookup_id(uniq_id)
			except Exception as e:
				logging.error("Failed to search link in DB!")
				logging.exception(e)
			if entities:
				tg_file_ids = [i["tg_file_id"] for i in entities]
				logging.info("URL '%s' is found in DB. Sending with tg_file_ids = '%s'", url, str(tg_file_ids))
				ent_len = len(entities)
				if ent_len > 1:
					await upload_job(
						update,
						context,
						UploadJob(
							tg_file_id=",".join(tg_file_ids),
							message_id=effective_message_id,
							media_type="collection"
						)
					)
				elif ent_len:
					media_type = entities.pop()["media_type"]
					await upload_job(
						update,
						context,
						UploadJob(
							tg_file_id=tg_file_ids.pop(),
							message_id=effective_message_id,
							media_type=media_type
						)
					)
			else:
				async def upload_wrapper(job: UploadJob) -> None:
					try:
						if job.job_failed and job.job_failed_msg:
							return await send_text(update, context, reply_id=job.message_id, text=job.job_failed_msg)
						tg_file_ids = await upload_job(update, context, job)
						if tg_file_ids:
							if job.media_type == "collection" and job.save_items:
								for i in job.media_collection:
									storage.add_media(tg_file_ids=[i.tg_file_id], media_url=i.effective_url, media_type=i.media_type, origin="instagram")
							else:
								storage.add_media(tg_file_ids=[','.join(tg_file_ids)], media_url=job.url, media_type=job.media_type, origin="instagram")
					except Exception as e:
						logging.error("Exception occurred while performing upload callback!")
						logging.exception(e)
					finally:
						uploader.process_done(job.uniq_id)
						uploader.remove_callback(job.message_id)

				uploader.add_callback(effective_message_id, upload_wrapper, update, context)

				try:
					downloader.queue_task(DownloadJob.build(
						url=url,
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
			pool_size=int(os.environ.get("UPLOAD_POOL_SIZE", default=warp_beacon.scrapler.CONST_CPU_COUNT)),
			loop=loop
		)
		downloader = warp_beacon.scrapler.AsyncDownloader(
			workers_count=int(os.environ.get("WORKERS_POOL_SIZE", default=warp_beacon.scrapler.CONST_CPU_COUNT)),
			uploader=uploader
		)
		downloader.start()
		uploader.start()

		# Create the Application and pass it your bot's token.
		tg_token = os.environ.get("TG_TOKEN", default=None)
		application = Application.builder().token(tg_token).concurrent_updates(True).build()

		# on different commands - answer in Telegram
		application.add_handler(CommandHandler("start", start))
		application.add_handler(CommandHandler("random", random))
		application.add_handler(CommandHandler("help", help_command))

		# on non command i.e message - echo the message on Telegram
		application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

		allow_loop = True
		try:
			loop.run_until_complete(application.initialize())
			if application.post_init:
				loop.run_until_complete(application.post_init(application))
			loop.run_until_complete(application.updater.start_polling())
			loop.run_until_complete(application.start())
			while allow_loop:
				try:
					loop.run_forever()
				except (KeyboardInterrupt, SystemExit) as e:
					allow_loop = False
					raise e
				except Exception as e:
					logging.error("Main loop Telegram error!")
					logging.exception(e)
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
