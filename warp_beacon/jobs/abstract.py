import os
from abc import ABC
from typing import TypedDict
from typing_extensions import Unpack
import uuid

from pyrogram.enums import ChatType

from warp_beacon.jobs import Origin
from warp_beacon.jobs.types import JobType

class JobSettings(TypedDict):
	job_id: uuid.UUID
	message_id: int
	chat_id: int
	user_id: int
	placeholder_message_id: int
	local_media_path: str
	local_compressed_media_path: str
	media_info: dict
	url: str
	uniq_id: str
	tg_file_id: str
	in_process: bool
	media_type: JobType
	job_failed: bool
	job_failed_msg: str
	job_warning: bool
	job_warning_message: str
	effective_url: str
	save_items: bool
	media_collection: list
	job_origin: Origin
	canonical_name: str
	is_message_to_admin: bool
	message_text: str
	source_username: str
	unvailable_error_count: int
	geoblock_error_count: int
	account_switches: int
	bad_proxy_error_count: int
	yt_auth: bool
	session_validation: bool
	chat_type: ChatType
	account_admins: str
	job_postponed_until: int
	message_leftover: str
	replay: bool
	short_text: bool
	scroll_content: bool
	last_pk: int

class AbstractJob(ABC):
	job_id: uuid.UUID = None
	message_id: int = 0
	user_id: int = 0
	chat_id: int = 0
	placeholder_message_id: int = 0
	local_media_path: str = ""
	local_compressed_media_path: str = ""
	media_info: dict = {}
	url: str = ""
	uniq_id: str = ""
	tg_file_id: str = ""
	media_type: JobType = JobType.VIDEO
	in_process: bool = False
	job_warning: bool = False
	job_warning_message: str = ""
	job_failed: bool = False
	job_failed_msg: str = ""
	effective_url: str = ""
	save_items: bool = False
	media_collection: list = []
	job_origin: Origin = Origin.UNKNOWN
	canonical_name: str = ""
	is_message_to_admin: bool = False
	message_text: str = ""
	source_username: str = ""
	unvailable_error_count: int = 0
	geoblock_error_count: int = 0
	account_switches: int = 0
	bad_proxy_error_count: int = 0
	yt_auth: bool = False
	session_validation: bool = False
	chat_type: ChatType = None
	account_admins: str = None
	job_postponed_until: int = -1
	message_leftover: str = ""
	replay: bool = False
	short_text: bool = False
	scroll_content: bool = False
	last_pk: int = 0

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

	def is_empty(self) -> bool:
		if self.media_type == JobType.COLLECTION:
			if not self.media_collection:
				return True
		elif not self.local_media_path:
			return True
		return False

	def to_dict(self) -> dict:
		d = {}
		for key in dir(self.__class__):
			if not key.startswith('_'):
				value = getattr(self, key)
				if not callable(value):
					d[key] = value
					
		return d

	def remove_files(self) -> bool:
		if self.media_type == JobType.COLLECTION:
			for i in self.media_collection:
				for j in i:
					if os.path.exists(j.local_media_path):
						os.unlink(j.local_media_path)
		else:
			if os.path.exists(self.local_media_path):
				os.unlink(self.local_media_path)
			if self.local_compressed_media_path:
				if os.path.exists(self.local_compressed_media_path):
					os.unlink(self.local_compressed_media_path)
