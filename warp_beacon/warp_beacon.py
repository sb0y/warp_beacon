import os
import sys
import uuid
import secrets
import hashlib
import argparse

from warp_beacon.telegram.bot import Bot

#import logging

def generate_uuid() -> str:
	return str(uuid.uuid4())

def generate_device_id(seed: str = None) -> str:
	raw = secrets.token_hex(8) if not seed else seed.encode()
	hex_part = hashlib.md5(raw).hexdigest()[:16]
	return f"android-{hex_part}"

def main() -> None:
	parser = argparse.ArgumentParser(description="Warp Beacon Telegram bot.")
	parser.add_argument("--uuid", action="store_true", help="Generate UUID")
	parser.add_argument("--generate-device-id", type=str, metavar="INSTAGRAM_LOGIN", help="Generate device_id with account login")

	args = parser.parse_args()

	if args.uuid:
		print(generate_uuid())
	elif args.generate_device_id:
		print(generate_device_id(args.generate_device_id))
	else:
		bot = Bot(
			tg_bot_name=os.environ.get("TG_BOT_NAME", default=None),
			tg_token=os.environ.get("TG_TOKEN", default=None),
			tg_api_id=os.environ.get("TG_API_ID", default=None),
			tg_api_hash=os.environ.get("TG_API_HASH", default=None)
		)
		bot.start()
	sys.exit(0)