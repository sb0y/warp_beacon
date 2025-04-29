#from typing import TypedDict
from typing_extensions import Unpack

from warp_beacon.jobs.upload_job import UploadJob
from warp_beacon.jobs.abstract import AbstractJob, JobSettings

#import logging

class DownloadJob(AbstractJob):
	def __init__(self, **kwargs: Unpack[JobSettings]) -> None:
		super(DownloadJob, self).__init__(**kwargs)

	@staticmethod
	def build(**kwargs: Unpack[JobSettings]) -> "DownloadJob":
		return DownloadJob(**kwargs)
	
	def to_upload_job(self, **kwargs: Unpack[JobSettings]) -> AbstractJob:
		d = self.to_dict()
		d.update(kwargs)
		if "media_collection" in d:
			for index, _ in enumerate(d["media_collection"]):
				for k, _ in enumerate(d["media_collection"][index]):
					d["media_collection"][index][k] = UploadJob.build(**d["media_collection"][index][k])
		return UploadJob.build(**d)