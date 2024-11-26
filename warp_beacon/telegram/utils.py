from typing import Union

import re
import requests

from pyrogram.types import Message

from warp_beacon.jobs import Origin
from warp_beacon.jobs.types import JobType

import logging

class Utils(object):
	expected_patronum_compiled_re = re.compile(r'Expected ([A-Z]+), got ([A-Z]+) file id instead')
	canonical_link_resolve_re = re.compile(r'<link.*rel="canonical".*href="([^"]+)"\s*/?>')

	@staticmethod
	def extract_file_id(message: Message) -> Union[None, str]:
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
	def extract_youtu_be_link(url: str) -> str:
		try:
			response = requests.get(
				url=url,
				allow_redirects=False
			)
			return response.headers["Location"]
		except Exception as e:
			logging.error("Failed to extract YouTube link!")
			logging.exception(e)

		return ''
	
	@staticmethod
	def resolve_ig_share_link(url: str) -> str:
		# expected url: https://www.instagram.com/share/reel/BAHtk2AamB
		# result url: https://www.instagram.com/reel/DAKjQgUNzuH/
		try:
			if "instagram.com/" in url and "share/" in url:
				content = requests.get(url).text
				res = re.search(Utils.canonical_link_resolve_re, content)
				new_url = res.group(1).strip()
				logging.info("Converted IG share link to '%s'", new_url)
				return new_url
		except Exception as e:
			logging.error("Failed to convert IG share link!")
			logging.exception(e)

		return url

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
	def extract_message_author(message: Message) -> str:
		if message.from_user:
			if message.from_user.username:
				return message.from_user.username
			if message.from_user.id:
				return str(message.from_user.id)
		if message.sender_chat:
			if message.sender_chat.username:
				return message.sender_chat.username
			if message.sender_chat.title:
				return message.sender_chat.title
		return ''