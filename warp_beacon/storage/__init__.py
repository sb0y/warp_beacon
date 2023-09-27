import os
import time
from urllib.parse import urlparse
import pathlib
import shutil

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
		pass

	@staticmethod
	def compute_uniq(url: str) -> str:
		path = urlparse(url).path.strip('/')
		return path
	
	def db_find(self, uniq_id: str) -> str:
		document = self.db.find_one({"uniq_id": uniq_id})
		if not document:
			return ""
		return document["local_media_path"]
	
	def db_lookup(self, url: str) -> str:
		uniq_id = self.compute_uniq(url)
		local_path = self.db_find(uniq_id)
		return local_path
	
	def add_media(self, url: str, local_path: str) -> int:
		path = pathlib.Path(local_path)
		media_ext = path.suffix
		media_filename = time.time()
		store_local_path = "%s/%s%s" % (VIDEO_STORAGE_DIR, media_filename, media_ext)
		shutil.copyfile(local_path, store_local_path)
		uniq_id = self.compute_uniq(url)
		media_id = self.db.insert_one({"uniq_id": uniq_id, "local_media_path": store_local_path}).inserted_id
		return media_id


