import logging

import asyncio
import hashlib

from pyrogram.enums import ParseMode
from pyrogram.errors.exceptions.bad_request_400 import MessageNotModified
from pyrogram import Client
from warp_beacon.telegram.types import ReportType

class ProgressBar(object):
	MAX_PROGRESS_RENDER_SIZE = 1_500_000 # 1 MB

	def __init__(self, client: Client) -> None:
		self._next_threshold = 20
		self.client = client
		self.complete = False

	def is_complete(self) -> bool:
		return self.complete

	def make_progress_bar(self, current: int, total: int, length: int = 10) -> str:
		"""
		Returns string
		[████▌────] 55%
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
		return f"<b>[{pbar}] {round(percent)}%</b>"

	def format_size_si(self, bytes_num: int) -> str:
		units = [("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024), ("B", 1)]
		for unit_name, unit_value in units:
			if bytes_num >= unit_value:
				value = bytes_num / unit_value
				return f"{value:.2f} {unit_name}"
		return "0 B"

	def make_emoji_progress_bar(self, percent: int, length: int = 10) -> str:
		"""
		Builds an emoji progress bar.

		Args:
			percent: int from 0 to 100
			length: total number of emoji cells

		Returns:
			String like "[🟩🟩🟩⬜️⬜️⬜️⬜️⬜️⬜️⬜️] 30%"
		"""
		filled = int(percent * length / 100 + 0.5)
		empty  = length - filled
		pbar = "🟩" * filled + "⬜️" * empty
		return f"[{pbar}] {percent}%"

	def _on_edit_done(self, task: asyncio.Task) -> None:
		exc = task.exception()
		if not exc:
			return
		if isinstance(exc, MessageNotModified):
			logging.warning("bad_request_400.MessageNotModified")
		else:
			logging.exception("Error in edit_message_caption", exc_info=exc)

	async def progress_callback(self, current: int, total: int, chat_id: int | str, message_id: int, operation: str, report_type: ReportType, label: str = "") -> None:
		if report_type == ReportType.PROGRESS:
			return await self.render_progress_bar(current=current, total=total, chat_id=chat_id, message_id=message_id, operation=operation, label=label)
		elif report_type == ReportType.ANNOUNCE:
			return self.render_progress_announce(chat_id=chat_id, message_id=message_id, label=label)

	def render_progress_announce(self, chat_id: int | str, message_id: int, label: str) -> None:
		try:
			#await self.client.edit_message_caption(chat_id, message_id, f"{pbar} <b>{operation}</b> {label}", ParseMode.HTML)
			# we don't need to wait completion, waste of time and resources
			task = self.client.loop.create_task(
				self.client.edit_message_caption(chat_id, message_id, f"<b>{label}</b>", ParseMode.HTML)
			)
			task.add_done_callback(self._on_edit_done)
		except MessageNotModified:
			logging.warning("bad_request_400.MessageNotModified")
		except Exception as e:
			logging.warning("An error occurred while setup task to update progress bar")
			logging.exception(e)

	async def render_progress_bar(self, current: int, total: int, chat_id: int | str, message_id: int, operation: str, label: str = "") -> None:
		if total <= self.MAX_PROGRESS_RENDER_SIZE:
			return
		percent = 0
		if total:
			percent = round(current * 100 / (total or 1))
		if percent >= 100:
			return
		if total == 0 or percent >= self._next_threshold:
			#pbar = self.make_progress_bar(percent, 100, 25)
			pbar = self.make_emoji_progress_bar(percent, 10)
			logging.info("[Progress bar]: Operation: %s %d%%", operation, percent)
			try:
				# we don't need to wait completion, waste of time and resources
				text = f"{pbar}\n{operation}"
				if label:
					text += f"\n<code>{label}</code>"
				if total:
					text += f" <b>{self.format_size_si(total)}</b>"
				await self.client.edit_message_caption(chat_id, message_id, text, ParseMode.HTML)
				#task = self.client.loop.create_task(
				#	self.client.edit_message_caption(chat_id, message_id, text, ParseMode.HTML)
				#)
				#task.add_done_callback(self._on_edit_done)
			except MessageNotModified:
				logging.warning("bad_request_400.MessageNotModified")
			except Exception as e:
				logging.warning("An error occurred while setup task to update progress bar")
				logging.exception(e)
			if total > 0:
				self._next_threshold += 20

	@staticmethod
	def make_hash(chat_id: str | int, message_id: int, algorithm: str = 'sha256') -> str:
		s = f"{chat_id}:{message_id}"
		# md5, sha1, sha256
		h = hashlib.new(algorithm, s.encode('utf-8'))
		return h.hexdigest()