import os
from typing import Optional
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
	
	def db_find(self, uniq_id: str) -> dict:
		document = None
		ret = {}
		try:
			document = self.db.find_one({"uniq_id": uniq_id})
			if document:
				ret = {"uniq_id": document["uniq_id"], "tg_file_id": document["tg_file_id"]}
		except Exception as e:
			logging.error("Error occurred while trying to read from the database!")
			logging.exception(e)
		return ret
	
	def db_lookup(self, url: str) -> dict:
		uniq_id = self.compute_uniq(url)
		doc = self.db_find(uniq_id)
		return doc
	
	def db_lookup_id(self, uniq_id: str) -> dict:
		return self.db_find(uniq_id)
	
	def add_media(self, tg_file_id: str, media_url: str, origin: str) -> int:
		uniq_id = self.compute_uniq(media_url)
		media_id = self.db.insert_one({"uniq_id": uniq_id, "tg_file_id": tg_file_id, "origin": origin}).inserted_id
		return media_id
	
	def get_random(self) -> dict:
		doc = None
		ret = {}
		try:
			cursor = self.db.aggregate([
				{ "$match": { "tg_file_id": { "$exists": True } } },
				{ "$sample": { "size": 1 } }
			])
			logging.info(list(cursor))
			if cursor:
				tmp = list(cursor)
				if tmp:
					ret = tmp[-1]
		except Exception as e:
			logging.error("Error occurred while trying to read from the database!")
			logging.exception(e)
		return ret



