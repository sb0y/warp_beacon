import os

from warp_beacon.telegram.bot import Bot

#import logging

def main() -> None:
	bot = Bot(
		tg_bot_name=os.environ.get("TG_BOT_NAME", default=None),
		tg_token=os.environ.get("TG_TOKEN", default=None),
		tg_api_id=os.environ.get("TG_API_ID", default=None),
		tg_api_hash=os.environ.get("TG_API_HASH", default=None)
	)
	bot.start()