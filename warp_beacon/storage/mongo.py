import os

from pymongo import MongoClient

class DBClient(object):
	client = None

	def __init__(self) -> None:
		self.client = MongoClient(
			host=os.environ.get("MONGODB_HOST", default='127.0.0.1'),
			port=int(os.environ.get("MONGODB_PORT", default=27017)),
			username=os.environ.get("MONGODB_USER", default='root'),
			password=os.environ.get("MONGODB_PASSWORD", default="changeme")
		)

	def __del__(self) -> None:
		self.close()

	def close(self) -> None:
		if self.client:
			self.client.close()
			self.client = None