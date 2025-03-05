import os, io
import time
from enum import Enum
from typing import Optional

#from pyrogram.types import Message
from pyrogram.errors import RPCError, FloodWait
from pyrogram.enums import ParseMode

import warp_beacon
from warp_beacon.telegram.utils import Utils
#from warp_beacon.mediainfo.video import VideoInfo

import logging

class PlaceholderType(Enum):
	UNKNOWN = 0
	ANIMATION = 1
	DOCUMENT = 2
	PHOTO = 3

class PlaceHolder(object):
	pl_type: PlaceholderType = PlaceholderType.ANIMATION
	tg_file_id: str = None

	def __init__(self, pl_type: PlaceholderType, tg_file_id: str) -> None:
		self.pl_type = pl_type
		self.tg_file_id = tg_file_id

class PlaceholderMessage(object):
	bot = None
	placeholder = PlaceHolder(PlaceholderType.ANIMATION, None)

	def __init__(self, bot: "Bot") -> None:
		self.bot = bot

	def __del__(self) -> None:
		pass

	async def reuse_ph_animation(self, chat_id: int, reply_id: int, text: str) -> Optional["types.Message"]:
		reply = await self.bot.client.send_animation(
			chat_id=chat_id,
			animation=self.placeholder.tg_file_id,
			caption=text,
			reply_to_message_id=reply_id,
			parse_mode=ParseMode.HTML
		)

		return reply

	async def reuse_ph_photo(self, chat_id: int, reply_id: int, text: str) -> Optional["types.Message"]:
		reply = await self.bot.client.send_photo(
			chat_id=chat_id,
			photo=self.placeholder.tg_file_id,
			caption=text,
			reply_to_message_id=reply_id,
			parse_mode=ParseMode.HTML
		)

		return reply

	async def reuse_ph_document(self, chat_id: int, reply_id: int, text: str) -> Optional["types.Message"]:
		reply = await self.bot.client.send_document(
			chat_id=chat_id,
			document=self.placeholder.tg_file_id,
			caption=text,
			reply_to_message_id=reply_id,
			parse_mode=ParseMode.HTML
		)

		return reply

	async def create(self, chat_id: int, reply_id: int) -> int:
		retry_amount = 0
		max_retries = int(os.environ.get("TG_MAX_RETRIES", default=5))
		while not retry_amount >= max_retries:
			try:
				text = "<b>Loading, this may take a moment ...</b> ⏱️ "
				reply = None
				if self.placeholder.tg_file_id is None:
					ph_found = False
					for ph in ('/var/warp_beacon/placeholder.gif', "%s/../var/warp_beacon/placeholder.gif" % os.path.dirname(os.path.abspath(warp_beacon.__file__))):
						if not os.path.exists(ph):
							continue
						try:
							#pl_info = VideoInfo(ph)
							#pl_resolution = pl_info.get_demensions()
							reply = await self.bot.client.send_document(
								chat_id=chat_id,
								document=ph,
								force_document=False,
								caption=text,
								parse_mode=ParseMode.HTML,
								reply_to_message_id=reply_id,
								file_name=os.path.basename(ph),
								#width=pl_resolution["width"],
								#height=pl_resolution["height"],
								#duration=round(pl_info.get_duration()),
								#thumb=pl_info.generate_thumbnail()
							)
							self.placeholder = PlaceHolder(PlaceholderType.ANIMATION, Utils.extract_file_id(reply))
							ph_found = True
							break
						except Exception as e:
							logging.warning("Failed to send placeholder message!")
							logging.exception(e)
					if not ph_found:
						try:
							reply = await self.bot.client.send_animation(
								chat_id=chat_id,
								animation="https://bagrintsev.me/warp_beacon/placeholder_that_we_deserve.mp4",
								caption=text,
								reply_to_message_id=reply_id,
								parse_mode=ParseMode.HTML
							)
							self.placeholder = PlaceHolder(PlaceholderType.ANIMATION, Utils.extract_file_id(reply))
						except Exception as e:
							logging.error("Failed to download secret placeholder!")
							logging.exception(e)
							img = self.create_default_placeholder_img("Loading, this may take a moment ...")
							reply = await self.bot.client.send_photo(
								chat_id=chat_id,
								parse_mode=ParseMode.HTML,
								reply_to_message_id=reply_id,
								photo=img
							)
							self.placeholder = PlaceHolder(PlaceholderType.PHOTO, Utils.extract_file_id(reply))
				else:
					if self.placeholder.pl_type == PlaceholderType.ANIMATION:
						try:
							reply = await self.reuse_ph_animation(chat_id, reply_id, text)
						except ValueError as e:
							logging.warning("Failed to reuse tg_file_id!")
							#logging.exception(e)
							reply = await self.reuse_ph_document(chat_id, reply_id, text)
							self.placeholder.pl_type = PlaceholderType.DOCUMENT
					elif self.placeholder.pl_type == PlaceholderType.DOCUMENT:
						try:
							reply = await self.reuse_ph_document(chat_id, reply_id, text)
						except ValueError as e:
							logging.warning("Failed to reuse tg_file_id!")
							#logging.exception(e)
							reply = await self.reuse_ph_animation(chat_id, reply_id, text)
							self.placeholder.pl_type = PlaceholderType.ANIMATION
					else:
						reply = await self.reuse_ph_photo(chat_id, reply_id, text)
				return reply.id
			except FloodWait as e:
				logging.warning("FloodWait exception!")
				logging.exception(e)
				await self.bot.send_text(None, "Telegram error: %s" % e.MESSAGE)
				time.sleep(e.value)
			except Exception as e:
				logging.error("Failed to create placeholder message!")
				logging.exception(e)
				retry_amount += 1
				time.sleep(2)

		return 0

	def create_default_placeholder_img(self, text: str, width: int = 800, height: int = 1280) -> io.BytesIO:
		from PIL import Image, ImageDraw, ImageFont
		bio = io.BytesIO()
		bio.name = 'placeholder.png'
		img = Image.new("RGB", (width, height), (255, 255, 255))
		draw = ImageDraw.Draw(img)
		font = ImageFont.load_default(size=48)
		_, _, w, h = draw.textbbox((0, 0), text, font=font)
		draw.text(((width-w)/2, (height-h)/2), text, font=font, fill="#000")
		img.save(bio, 'PNG')
		bio.seek(0)

		return bio

	async def update_text(self, chat_id: int, placeholder_message_id: int, placeholder_text: str) -> None:
		try:
			await self.bot.client.edit_message_caption(
				chat_id=chat_id,
				message_id=placeholder_message_id,
				caption=" ⚠️ <b>%s</b>" % placeholder_text,
				parse_mode=ParseMode.HTML
			)
		except Exception as e:
			logging.error("Failed to update placeholder message!")
			logging.exception(e)

	async def remove(self, chat_id: int, placeholder_message_id: int) -> None:
		try:
			await self.bot.client.delete_messages(chat_id, (placeholder_message_id,))
		except Exception as e:
			logging.error("Failed to remove placeholder message!")
			logging.exception(e)
