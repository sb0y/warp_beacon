import os
#from typing import Optional
from enum import Enum

from urllib.parse import urlparse, parse_qs

from warp_beacon.storage.mongo import DBClient

import logging

class UrlParseMode(Enum):
	OTHER = 0
	YT_MUSIC = 1
	YT_SHORTS = 2
	YOUTUBE = 3

VIDEO_STORAGE_DIR = os.environ.get("VIDEO_STORAGE_DIR", default="/var/warp_beacon/videos")

class Storage(object):
	client = None
	db = None
	def __init__(self, client: DBClient) -> None:
		if not os.path.isdir(VIDEO_STORAGE_DIR):
			os.mkdir(VIDEO_STORAGE_DIR)
		self.client = client
		self.db = self.client.client.media.media

	def __del__(self) -> None:
		self.client.close()

	@staticmethod
	def compute_uniq(url: str) -> str:
		parse_mode = UrlParseMode.OTHER
		if "music.youtube.com/" in url:
			parse_mode = UrlParseMode.YT_MUSIC
		elif "youtube.com/shorts/" in url:
			parse_mode = UrlParseMode.YT_SHORTS
		elif "youtube.com/" in url:
			parse_mode = UrlParseMode.YOUTUBE

		if parse_mode is not UrlParseMode.OTHER and parse_mode is not UrlParseMode.YT_SHORTS:
			purl = urlparse(url)
			qs = parse_qs(purl.query)
			yt_vid_id_list = qs.get('v', None)
			yt_vid_id = yt_vid_id_list.pop() if yt_vid_id_list else ""
			if yt_vid_id:
				path = urlparse(url).path.strip('/').replace("watch", ("yt_music" if parse_mode is UrlParseMode.YT_MUSIC else "youtube"))
				return f"{path}/{yt_vid_id}".strip('/')
			else:
				raise ValueError(f"Failed to generate uniq_id for url '{url}'")
			
		path = urlparse(url).path.strip('/')
		return path
	
	def db_find(self, uniq_id: str, origin: str = "") -> list[dict]:
		document = None
		ret = []
		try:
			logging.debug("uniq_id to search is '%s'", uniq_id)
			find_opts = {"uniq_id": uniq_id}
			if origin:
				find_opts["origin"] = origin
			cursor = self.db.find(find_opts)
			for document in cursor:
				ret.append(
				{
					"uniq_id": document["uniq_id"],
					"tg_file_id": document["tg_file_id"],
					"media_type": document["media_type"],
					"canonical_name": document.get("canonical_name")
				})
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
	
	def add_media(self, tg_file_ids: list[str], media_url: str, media_type: str, origin: str, canonical_name: str = "") -> list[int]:
		uniq_id = self.compute_uniq(media_url)
		media_ids = []
		for tg_file_id in tg_file_ids:
			if not tg_file_id:
				logging.warning("Passed empty `tg_file_id`! Skipping.")
				continue
			if self.db_lookup_id(uniq_id):
				logging.info("Detected existing uniq_id, skipping storage write operation")
				continue
			media_ids += str(self.db.insert_one(
			{
				"uniq_id": uniq_id,
				"media_type": media_type,
				"tg_file_id": tg_file_id,
				"origin": origin,
				"canonical_name": canonical_name
			}).inserted_id)

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