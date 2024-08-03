import os
import pathlib
from abc import ABC, abstractmethod

from PIL import Image

import av

class MediaInfoAbstract(ABC):
	filename = ""
	container = None
	duration = 0.0

	def __init__(self, filename: str) -> None:
		self.filename = filename
		self.container = av.open(file=self.filename, mode='r')

	def __del__(self) -> None:
		if self.container:
			self.container.close()

	def get_duration(self) -> float:
		return self.duration

	@staticmethod
	def get_filesize(filename: str) -> float:
		return os.stat(filename).st_size

	@abstractmethod
	def get_finfo(cls, except_info: tuple=()) -> dict:
		raise NotImplementedError

	@staticmethod
	def shrink_image_to_fit(image: Image, size: tuple = (320, 320)) -> Image:
		image.thumbnail(size, Image.Resampling.LANCZOS)
		#image.save(
		#	"/tmp/test.th.jpg",
		#	quality=80,
		#)
		return image

	def generate_filepath(self, base_filepath: str, postfix: str = "silenced") -> str:
		path_info = pathlib.Path(base_filepath)
		ext = path_info.suffix
		old_filename = path_info.stem
		new_filename = "%s_%s%s" % (old_filename, postfix, ext)
		new_filepath = "%s/%s" % (os.path.dirname(base_filepath), new_filename)

		return new_filepath
