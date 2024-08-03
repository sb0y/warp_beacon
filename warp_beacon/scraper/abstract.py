import os
import pathlib

from abc import ABC, abstractmethod
from typing import Callable, Union

from PIL import Image

import logging

class ScraperAbstract(ABC):
	def __init__(self) -> None:
		pass

	def __del__(self) -> None:
		pass

	@abstractmethod
	def download(self, url: str) -> bool:
		raise NotImplementedError

	@abstractmethod
	def _download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
		raise NotImplementedError

	@staticmethod
	def convert_webp_to_png(src_file: str) -> str:
		try:
			if os.path.exists(src_file):
				path_info = pathlib.Path(src_file)
				old_filename = path_info.stem
				new_filename = "%s_converted.%s" % (old_filename, "png")
				new_filepath = "%s/%s" % (os.path.dirname(src_file), new_filename)
				with Image.open(src_file).convert('RGB') as img:
					img.save(new_filepath, 'png')
				os.unlink(src_file)
				return new_filepath
		except Exception as e:
			logging.error("Failed to convert webp file to png!")
			logging.exception(e)

		return ''


