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
		db_id = ""
		try:
			# check if job not already in storage
			find_opts = {"uniq_id": job.uniq_id, "message_id": job.message_id, "chat_id": job.chat_id}
			if self.db.find_one(find_opts) is not None:
				logging.info("Job already in storage skipping write")
				return 0
			#
			job_serilized = pickle.dumps(job)
			db_id = self.db.insert_one(
			{
				"job_data": job_serilized,
				"uniq_id": job.uniq_id,
				"message_id": job.message_id,
				"chat_id": job.chat_id
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
				ret.append({
					"_id": document["_id"],
					"job": pickle.loads(document["job_data"]),
					"uniq_id": document.get("uniq_id"),
					"message_id": document.get("message_id"),
					"chat_id": document.get("chat_id")
				})
			if clean:
				self.db.delete_many({})
		except Exception as e:
			logging.error("Failed to get failed jobs!")
			logging.exception(e)
		return ret
	
	def remove_failed_job(self, uniq_id: str) -> bool:
		try:
			result = self.db.delete_one({"uniq_id": uniq_id})
			if result.deleted_count > 0:
				return True
		except Exception as e:
			logging.error("Failed to remove failed job!", exc_info=e)

		return False