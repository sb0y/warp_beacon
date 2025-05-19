import logging
from multiprocessing import Pipe
from pyrogram import Client
from warp_beacon.telegram.progress_bar import ProgressBar
from warp_beacon.telegram.types import ReportType

class DownloadStatus(object):
	status_pipe = None
	child_conn = None
	client = None
	progress_bars = None

	def __init__(self, client: Client) -> None:
		self.progress_bars = {}
		self.client = client
		self.status_pipe, self.child_conn = Pipe()

	async def handle_message(self, msg: dict, progress_bar: ProgressBar) -> None:
		op = "Downloading"
		if msg.get("media_type", None):
			op += f" {msg['media_type']}"
		await progress_bar.progress_callback(
			current=msg.get("current", 0),
			total=msg.get("total", 0),
			message_id=msg.get("message_id", 0),
			chat_id=msg.get("chat_id", 0),
			operation=op,
			report_type=msg.get("report_type", ReportType.PROGRESS),
			label=msg.get("label", "")
		)

	def on_status(self) -> None:
		msg = self.status_pipe.recv()
		if not msg:
			logging.warning("Empty status message!")
			return
		logging.info("Received pipe message: %s", msg)
		message_id = msg.get("message_id", 0)
		chat_id = msg.get("chat_id", 0)
		a_key = f"{message_id}:{chat_id}"
		progress_bar = None
		if a_key not in self.progress_bars:
			progress_bar = ProgressBar(self.client)
			self.progress_bars[a_key] = progress_bar
		else:
			progress_bar = self.progress_bars[a_key]
		task = self.client.loop.create_task(self.handle_message(msg, progress_bar))
		if msg.get("completed", False):
			task.add_done_callback(lambda _: self.progress_bars.pop(a_key, None))