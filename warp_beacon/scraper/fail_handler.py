import os

import pickle
from pymongo import MongoClient

from warp_beacon.jobs.download_job import DownloadJob

import logging

class FailHandler(object):
	client = None
	db = None
	def __init__(self) -> None:
		self.client = MongoClient(
			host=os.environ.get("MONGODB_HOST", default='127.0.0.1'), 
			port=int(os.environ.get("MONGODB_PORT", default=27017)),
			username=os.environ.get("MONGODB_USER", default='root'),
			password=os.environ.get("MONGODB_PASSWORD", default="changeme"))
		self.db = self.client.media.failed_jobs

	def __del__(self) -> None:
		if self.client:
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
	
	def get_failed_jobs(self) -> list:
		ret = []
		try:
			cursor = self.db.find()
			for document in cursor:
				ret.append(pickle.loads(document["job_data"]))
			self.db.delete_many({})
		except Exception as e:
			logging.error("Failed to get failed jobs!")
			logging.exception(e)
		return ret
