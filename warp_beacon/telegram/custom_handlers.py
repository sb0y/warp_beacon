import os
import sys
from pathlib import Path
import importlib.util
import logging

from pyrogram import Client
from pyrogram.types import Message

class CustomHandlers(object):
	def __init__(self) -> None:
		self.handlers = []
		self.ch_dir = os.environ.get("CUSTOM_HANDLERS_DIR", default="/var/warp_beacon/custom_handlers")
		try:
			if self.ch_dir and os.path.isdir(self.ch_dir):
				for f in os.listdir(self.ch_dir):
					handler_path = f"{self.ch_dir}/{f}"
					if f.endswith(".py"):
						logging.info("[CUSTOM HANDLERS]: Found file '%s'", handler_path)
						handler = self.load_class_from_file(file_path=handler_path)
						self.handlers.append(handler)
			else:
				logging.info("[CUSTOM HANDLERS]: Directory '%s' is not exists, skipping custom handlers init", self.ch_dir)
		except Exception as e:
			logging.warning("[CUSTOM HANDLERS]: Exception occurred while custom handlers init!", exc_info=e)

	def load_class_from_file(self, file_path: str):
		module_name = Path(file_path).stem # module name from file name
		class_name = module_name
		spec = importlib.util.spec_from_file_location(module_name, file_path)
		module = importlib.util.module_from_spec(spec)
		sys.modules[module_name] = module
		spec.loader.exec_module(module)

		logging.info("[CUSTOM HANDLERS]: Loaded custom handler '%s'", class_name)

		cls = getattr(module, module_name, None)
		if isinstance(cls, type):
			return cls()

		raise RuntimeError(f"No handler found in {file_path}")
	
	async def exec_handlers(self, client: Client, message: Message, message_text: str) -> None:
		try:
			if not self.handlers:
				return
			for h in self.handlers:
				await h.exec(client, message, message_text)
		except Exception as e:
			logging.warning("[CUSTOM HANDLERS]: Exception occurred while running custom handler!", exc_info=e)