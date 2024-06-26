from abc import ABC, abstractmethod
from typing import TypedDict
from typing_extensions import Unpack
import uuid

class JobSettings(TypedDict):
	job_id: uuid.UUID
	message_id: int
	local_media_path: str
	media_info: dict
	url: str
	uniq_id: str
	tg_file_id: str
	in_process: bool
	job_failed: bool
	media_type: str
	job_failed_msg: str
	effective_url: str
	save_items: bool
	media_collection: list

class AbstractJob(ABC):
	job_id: uuid.UUID = None
	message_id: int = 0
	local_media_path: str = ""
	media_info: dict = {}
	url: str = ""
	uniq_id: str = ""
	tg_file_id: str = ""
	media_type: str = "video"
	in_process: bool = False
	job_failed: bool = False
	job_failed_msg: str = ""
	effective_url: str = ""
	save_items: bool = False
	media_collection: list = []

	def __init__(self, **kwargs: Unpack[JobSettings]) -> None:
		if kwargs:
			self.__dict__.update(kwargs)
		self.job_id = uuid.uuid4()

	def __del__(self) -> None:
		pass

	def __str__(self) -> str:
		return str(self.to_dict())

	def __repr__(self) -> str:
		return str(self.to_dict())

	def to_dict(self) -> dict:
		d = {}
		for key in dir(self.__class__):
			if not key.startswith('_'):
				value = getattr(self, key)
				if not callable(value):
					d[key] = value
					
		return d