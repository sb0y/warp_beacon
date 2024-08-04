from typing import TypedDict
from typing_extensions import Unpack

from warp_beacon.jobs.abstract import AbstractJob, JobSettings

class UploadJob(AbstractJob):
	def __init__(self, **kwargs: Unpack[JobSettings]) -> None:
		super(UploadJob, self).__init__(**kwargs)

	def __del__(self) -> None:
		pass

	@staticmethod
	def build(**kwargs: Unpack[JobSettings]) -> "UploadJob":
		return UploadJob(**kwargs)
	
	def to_download_job(self, **kwargs: Unpack[JobSettings]) -> AbstractJob:
		from warp_beacon.jobs.download_job import DownloadJob
		d = self.to_dict()
		d.update(kwargs)
		return DownloadJob.build(**d)
	
	def set_flag(self, key: str, value: bool) -> "UploadJob":
		if key in self.__dict__:
			self.__dict__[key] = value

		return self
