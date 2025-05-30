import pickle

import logging

from warp_beacon.storage.mongo import DBClient
from warp_beacon.jobs.download_job import DownloadJob

class FailHandler(object):
	client = None
	db = None
	def __init__(self, client: DBClient) -> None:
		self.client = client
		self.db = self.client.client.media.failed_jobs

	def __del__(self) -> None:
		self.client.close()

	def store_failed_job(self, job: DownloadJob) -> int:
		db_id = -1
		try:
			job_serilized = pickle.dumps(job)
			db_id = self.db.insert_one(
			{
				"job_data": job_serilized
			}).inserted_id
		except Exception as e:
			logging.error("Failed to store job as failed!")
			logging.exception(e)
		return db_id
	
	def get_failed_jobs(self, clean: bool = True) -> list:
		ret = []
		try:
			cursor = self.db.find()
			for document in cursor:
				ret.append(pickle.loads(document["job_data"]))
			if clean:
				self.db.delete_many({})
		except Exception as e:
			logging.error("Failed to get failed jobs!")
			logging.exception(e)
		return ret
