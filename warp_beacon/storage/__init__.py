import os
#from typing import Optional
import logging

from urllib.parse import urlparse

from pymongo import MongoClient

VIDEO_STORAGE_DIR = os.environ.get("VIDEO_STORAGE_DIR", default="/var/warp_beacon/videos")

class Storage(object):
	client = None
	db = None
	def __init__(self) -> None:
		if not os.path.isdir(VIDEO_STORAGE_DIR):
			os.mkdir(VIDEO_STORAGE_DIR)

		self.client = MongoClient(
			host=os.environ.get("MONGODB_HOST", default='127.0.0.1'), 
			port=int(os.environ.get("MONGODB_PORT", default=27017)),
			username=os.environ.get("MONGODB_USER", default='root'),
			password=os.environ.get("MONGODB_PASSWORD", default="changeme"))
		self.db = self.client.media.media

	def __del__(self) -> None:
		if self.client:
			self.client.close()

	@staticmethod
	def compute_uniq(url: str) -> str:
		path = urlparse(url).path.strip('/')
		return path
	
	def db_find(self, uniq_id: str) -> list[dict]:
		document = None
		ret = []
		try:
			logging.debug("uniq_id to search is '%s'", uniq_id)
			cursor = self.db.find({"uniq_id": uniq_id})
			for document in cursor:
				ret.append({"uniq_id": document["uniq_id"], "tg_file_id": document["tg_file_id"], "media_type": document["media_type"]})
		except Exception as e:
			logging.error("Error occurred while trying to read from the database!")
			logging.exception(e)
		return ret
	
	def db_lookup(self, url: str) -> dict:
		uniq_id = self.compute_uniq(url)
		doc = self.db_find(uniq_id)
		return doc
	
	def db_lookup_id(self, uniq_id: str) -> list[dict]:
		return self.db_find(uniq_id)
	
	def add_media(self, tg_file_ids: list[str], media_url: str, media_type: str, origin: str) -> list[int]:
		uniq_id = self.compute_uniq(media_url)
		media_ids = []
		for tg_file_id in tg_file_ids:
			if self.db_lookup_id(uniq_id):
				logging.info("Detected existing uniq_id, skipping storage write operation")
				continue
			media_ids += str(self.db.insert_one({"uniq_id": uniq_id, "media_type": media_type, "tg_file_id": tg_file_id, "origin": origin}).inserted_id)

		return media_ids
	
	def get_random(self) -> dict:
		ret = {}
		try:
			cursor = self.db.aggregate([
				{ "$match": { "tg_file_id": { "$exists": True } } },
				{ "$sample": { "size": 1 } }
			])
			tmp = list(cursor)
			if tmp:
				ret = tmp.pop()
		except Exception as e:
			logging.error("Error occurred while trying to read from the database!")
			logging.exception(e)
		return ret



