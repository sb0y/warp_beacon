from typing import TypedDict
from typing_extensions import Unpack

from jobs.upload_job import UploadJob
from jobs.abstract import AbstractJob, JobSettings

class DownloadJob(AbstractJob):
	def __init__(self, **kwargs: Unpack[JobSettings]) -> None:
		super(DownloadJob, self).__init__(**kwargs)
	def __del__(self) -> None:
		pass

	@staticmethod
	def build(**kwargs: Unpack[JobSettings]) -> "DownloadJob":
		return DownloadJob(**kwargs)
	
	def to_upload_job(self, **kwargs: Unpack[JobSettings]) -> AbstractJob:
		d = self.to_dict()
		d.update(kwargs)
		return UploadJob.build(**d)