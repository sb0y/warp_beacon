#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import signal
import logging

from urlextract import URLExtract

import scrapler
from storage import Storage
from mediainfo.video import VideoInfo
from uploader import AsyncUploader

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
uploader = AsyncUploader(
	pool_size=int(os.environ.get("UPLOAD_POOL_SIZE", default=3))
)
downloader = scrapler.AsyncDownloader(
	workers_count=int(os.environ.get("WORKERS_POOL_SIZE", default=scrapler.CONST_CPU_COUNT)),
	uploader=uploader
)

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
			db_doc = None
			tg_file_id = ""
			try:
				db_doc = storage.db_lookup(url)
			except Exception as e:
				logging.error("Failed to search link in DB!")
				logging.exception(e)
			if db_doc:
				tg_file_id = db_doc["tg_file_id"]
				logging.info("URL '%s' is found in DB. Sending with tg_file_id = '%s'", url, tg_file_id)
				try:
					await update.message.reply_video(
						video=tg_file_id, 
						reply_to_message_id=effective_message_id, 
						supports_streaming=False,
						disable_notification=True,
						write_timeout=int(os.environ.get("TG_WRITE_TIMEOUT", default=120)))
				except Exception as e:
					logging.error("Failed to send video with tg_file_id = '%s'!", tg_file_id)
					logging.exception(e)
			else:
				async def send(local_media_path: str) -> None:
					try:
						video_info = VideoInfo(local_media_path)
						media_info = video_info.get_finfo()
						logging.info("media file info: %s", media_info)
						thumb = video_info.generate_thumbnail()
						message = await update.message.reply_video(
							video=open(local_media_path, 'rb'), 
							reply_to_message_id=effective_message_id, 
							supports_streaming=True,
							disable_notification=True,
							duration=media_info["duration"],
							width=media_info["width"],
							height=media_info["height"],
							thumbnail=thumb,
							write_timeout=int(os.environ.get("TG_WRITE_TIMEOUT", default=120)))
						storage.add_media(tg_file_id=message.video.file_id, media_url=url, origin="instagram")
					except error.NetworkError as e:
						logging.error("Failed to upload due telegram limits :(")
						logging.exception(e)
						reply_text = "Unfortunately, Telegram limits were exceeded. Your video size is %.2f MB." % media_info["filesize"]
						await update.message.reply_text(reply_text, reply_to_message_id=effective_message_id)
					except Exception as e:
						logging.error("Error occurred!")
						logging.exception(e)
					finally:
						if os.path.exists(local_media_path):
							os.unlink(local_media_path)

				uploader.set_callback(send)

				logging.info("Downloading URL '%s' from instagram ...", url)
				try:
					downloader.queue_task(url)
				except Exception as e:
					logging.error("Failed to schedule download task!")
					logging.exception(e)
		return

	if chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
		await update.message.reply_text(reply_text, reply_to_message_id=effective_message_id)

def main() -> None:
	"""Start the bot."""
	# Create the Application and pass it your bot's token.
	application = Application.builder().token(os.environ.get("TG_TOKEN", default=None)).build()

	# on different commands - answer in Telegram
	application.add_handler(CommandHandler("start", start))
	application.add_handler(CommandHandler("help", help_command))

	# on non command i.e message - echo the message on Telegram
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
	# Run the bot until the user presses Ctrl-C
	application.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[signal.SIGTERM, signal.SIGINT, signal.SIGQUIT])
	downloader.stop_all()
	uploader.stop_all()


if __name__ == "__main__":
	main()