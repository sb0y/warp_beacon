import logging

import hashlib

from pyrogram.enums import ParseMode
from pyrogram.errors.exceptions.bad_request_400 import MessageNotModified
from pyrogram import Client

class ProgressBar(object):
	def __init__(self, client: Client) -> None:
		self._next_threshold = 20
		self.client = client

	def make_progress_bar(self, current: int, total: int, length: int = 10) -> str:
		"""
		Returns string
		[████▌────] 55.0%
		length — amount of characters in bar
		"""
		# fraction of completed job from 0.0 to 1.0
		frac = current / total if total else 0
		# how much "filled" cells
		filled = int(frac * length)
		# part between whole cells, optional may withdraw half
		half_block = ''
		if (frac * length) - filled >= 0.5:
			half_block = '▌'  # or '▏', '▍' and etc.
		# building bar
		pbar = '█' * filled + half_block + '─' * (length - filled - len(half_block))
		percent = frac * 100
		return f"[{pbar}] {round(percent)}%"
	
	def make_emoji_progress_bar(self, current: int, total: int, length: int = 10) -> str:
		"""
		Returns string:
		[🟩🟩🟩⬜️⬜️⬜️⬜️⬜️⬜️⬜️] 30.0%
		length — common number of emoji cells
		"""
		frac = (current / total) if total else 0
		filled_count = int(frac * length)
		empty_count = length - filled_count
		pbar = "🟩" * filled_count + "⬜️" * empty_count
		percent = frac * 100
		return f"[{pbar}] {round(percent)}%"

	async def progress_callback(self, current: int, total: int, chat_id: int | str, message_id: int, label: str) -> None:
		percent = current * 100 / total
		if percent >= self._next_threshold:
			#pbar = self.make_progress_bar(percent, 100, 25)
			pbar = self.make_emoji_progress_bar(percent, 100, 14)
			logging.info("[%s] Uploaded to Telegram %d%%", label, percent)
			try:
				await self.client.edit_message_caption(chat_id, message_id, f"{pbar}<br><b>Uploading <code>{label}</code></b>", ParseMode.HTML)
			except MessageNotModified:
				logging.warning("bad_request_400.MessageNotModified")
			except Exception as e:
				logging.warning("An error occurred while updating progress bar")
				logging.exception(e)
			self._next_threshold += 20

	@staticmethod
	def make_hash(chat_id: str | int, message_id: int, algorithm: str = 'sha256') -> str:
		s = f"{chat_id}:{message_id}"
		# md5, sha1, sha256
		h = hashlib.new(algorithm, s.encode('utf-8'))
		return h.hexdigest()