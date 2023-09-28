#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import signal
import logging

import multiprocessing

from urlextract import URLExtract

from scrapler import AsyncDownloader
from storage import Storage

from telegram import ForceReply, Update, Chat
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Enable logging
logging.basicConfig(
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

storage = Storage()
downloader = AsyncDownloader(
	workers_count=int(os.environ.get("WORKERS_POOL_SIZE", default=multiprocessing.cpu_count()))
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
	urls = extractor.find_urls(update.message.text)
	reply_text = "Wut?"
	if not urls:
		reply_text = "Your message should contains URLs"
	else:
		for url in urls:
			if "instagram.com" not in url:
				logging.info("Only instagram.com is now supported. Skipping.")
				continue
			media_path = ""
			try:
				media_path = storage.db_lookup(url)
			except Exception as e:
				logging.error("Failed to search link in DB!")
				logging.exception(e)
			if not media_path:
				logging.info("Downloading URL '%s' from instagram ...", url)
				task_id = None
				try:
					task_id = downloader.queue_task(url)
				except Exception as e:
					logging.error("Failed to schedule download task!")
					logging.exception(e)
				
				media_path = downloader.wait_result(task_id)
				try:
					storage.add_media(url, media_path)
				except Exception as e:
					logging.error("Failed to write link to DB!")
					logging.exception(e)
			else:
				logging.info("URL was '%s' found in DB", url)
			
			try:
				await update.message.reply_video(
					video=open(media_path, 'rb'), 
					reply_to_message_id=effective_message_id, 
					supports_streaming=False)
				if "/tmp/" in media_path:
					os.unlink(media_path)
			except Exception as e:
				logging.error("Error occurred!")
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


if __name__ == "__main__":
	main()