import os
from abc import ABC, abstractmethod

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