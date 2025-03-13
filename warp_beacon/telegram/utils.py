from typing import Union, Optional

import re

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.types import ChatMember
from pyrogram import enums

from warp_beacon.jobs import Origin
from warp_beacon.jobs.types import JobType

import logging

class Utils(object):
	expected_patronum_compiled_re = re.compile(r'Expected ([A-Z]+), got ([A-Z]+) file id instead')
	mention_re = re.compile(r'@[A-Za-z0-9_.]{4,}')

	@staticmethod
	def extract_file_id(message: Message) -> Optional[str]:
		possible_attrs = ("video", "photo", "audio", "animation", "document")
		for attr in possible_attrs:
			if hasattr(message, attr):
				_attr = getattr(message, attr, None)
				if _attr:
					tg_id = getattr(_attr, "file_id", None)
					if tg_id:
						return tg_id
		return None

	@staticmethod
	def extract_origin(url: str) -> Origin:
		if "instagram.com/" in url:
			return Origin.INSTAGRAM

		if "youtube.com/" in url and "shorts/" in url:
			return Origin.YT_SHORTS

		if "youtube.com/" in url and "music." in url:
			return Origin.YT_MUSIC

		if "youtu.be/" in url:
			return Origin.YOUTU_BE

		if "youtube.com/" in url:
			return Origin.YOUTUBE

		return Origin.UNKNOWN

	@staticmethod
	def parse_expected_patronum_error(err_text: str) -> tuple:
		'''
			Input example: 'Expected VIDEO, got ANIMATION file id instead'
		'''
		capture = re.match(Utils.expected_patronum_compiled_re, err_text)
		expected_value, got_value = capture[1], capture[2]

		return JobType[expected_value], JobType[got_value]

	@staticmethod
	def chunker(seq: list, size: int) -> list:
		return (seq[pos:pos + size] for pos in range(0, len(seq), size))

	@staticmethod
	def extract_message_text(message: Message) -> str:
		if hasattr(message, "text") and message.text:
			return message.text
		if hasattr(message, "caption") and message.caption:
			return message.caption

		return ''

	@staticmethod
	async def extract_message_author(message: Message) -> str:
		if message.from_user:
			if message.from_user.username:
				return message.from_user.username
			if message.from_user.first_name:
				return message.from_user.first_name
			if message.from_user.id:
				return str(message.from_user.mention(style=enums.ParseMode.HTML))
		if message.sender_chat:
			if message.sender_chat.username:
				return message.sender_chat.username
			if message.sender_chat.title:
				return message.sender_chat.title
		return ''

	@staticmethod
	def compute_leftover(urls: list, message: str) -> str:
		msg_leftover = ""
		if len(message) > sum(len(u) for u in urls):
			msg_leftover = message
			for u in urls:
				msg_leftover = msg_leftover.replace(u, '')
		return msg_leftover.strip()
	
	@staticmethod
	async def find_chat_user_by_id(client: Client, chat_id: int, user_id: int) -> Optional[ChatMember]:
		ret = None
		async for member in client.get_chat_members(chat_id):
			user_id = 0
			if member.user.id == user_id:
				ret = member.user
				break
		return ret

	@staticmethod
	def handle_mentions(chat_id: int, client: Client, message: str) -> str:
		try:
			username = ''
			members = client.get_chat_members(chat_id)
			mentions = Utils.mention_re.findall(message)
			for mention in mentions:
				username = mention[1:].strip()
				if username:
					user_id = 0
					for member in members:
						if member.user.username == username:
							user_id = member.user.id
							break
					if user_id:
						message.replace(f"@{username}", f'<a href="tg://user?id={user_id}">{username}</a>')
		except Exception as e:
			logging.warning("Exception occurred while handling TG mentions!")
			logging.exception(e)
		return message
