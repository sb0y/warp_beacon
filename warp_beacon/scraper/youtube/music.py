import io
from typing import Optional

import logging

import time
import json

import yt_dlp

from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract
from warp_beacon.scraper.exceptions import NotFound, FileTooBig, Unavailable

class YoutubeMusicScraper(YoutubeAbstract):
	YT_MAX_RETRIES_DEFAULT = 3
	YT_PAUSE_BEFORE_RETRY_DEFAULT = 3
	YT_TIMEOUT_DEFAULT = 2
	YT_TIMEOUT_INCREMENT_DEFAULT = 60

	def _download(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 0) -> list:
		res = []
		try:
			yt = self.build_yt(url, session=session)
			
			stream = yt.streams.get_audio_only()
			
			if not stream:
				raise NotFound("No suitable audio stream found")
			
			logging.info("Announced audio file size: '%d'", stream.filesize)
			if stream.filesize > 2e+9:
				logging.warning("Downloading size reported by YouTube is over than 2 GB!")
				raise FileTooBig("YouTube file is larger than 2 GB")
			logging.info("Operation timeout is '%d'", timeout)
			local_file = stream.download(
				output_path=self.DOWNLOAD_DIR,
				max_retries=0,
				timeout=timeout,
				skip_existing=False,
				filename_prefix='yt_download_'
			)
			logging.debug("Temp filename: '%s'", local_file)
			res.append({
				"local_media_path": self.rename_local_file(local_file),
				"performer": yt.author,
				"thumb": thumbnail,
				"canonical_name": yt.title,
				"media_type": JobType.AUDIO
			})
		except Exception:
			raise Unavailable("Content unavailable")

		return res

	def build_yt_dlp(self, timeout: int = 60) -> yt_dlp.YoutubeDL:
		auth_data = {}
		with open(self.YT_SESSION_FILE % self.account_index, 'r', encoding="utf-8") as f:
			auth_data = json.loads(f.read())
		time_name = str(time.time()).replace('.', '_')
		ydl_opts = {
			'socket_timeout': timeout,
			'outtmpl': f'{self.DOWNLOAD_DIR}/yt_download_{time_name}.%(ext)s',
			'format': 'bestaudio[ext=m4a]/bestaudio/best',
			'noplaylist': True,
			'keepvideo': False,
			'tv_auth': auth_data
		}

		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			logging.info("Using proxy DSN '%s'", proxy_dsn)
			if proxy_dsn:
				ydl_opts["proxy"] = proxy_dsn

		return yt_dlp.YoutubeDL(ydl_opts)

	def _download_yt_dlp(self, url: str, timeout: int = 60, thumbnail: Optional[io.BytesIO] = None) -> list:
		res = []
		with self.build_yt_dlp(timeout) as ydl:
			info = ydl.extract_info(url, download=True)
			local_file = ydl.prepare_filename(info)
			logging.debug("Temp filename: '%s'", local_file)
			res.append({
				"local_media_path": local_file,
				"performer": info.get("uploader", "Unknown"),
				"thumb": thumbnail,
				"canonical_name": info.get("title", ''),
				"media_type": JobType.AUDIO
			})

		return res
