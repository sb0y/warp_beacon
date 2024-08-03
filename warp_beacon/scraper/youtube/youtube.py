from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract

from pytubefix import YouTube

import logging

class YoutubeScraper(YoutubeAbstract):
	YT_MAX_RETRIES_DEFAULT = 8
	YT_PAUSE_BEFORE_RETRY_DEFAULT = 3
	YT_TIMEOUT_DEFAULT = 2
	YT_TIMEOUT_INCREMENT_DEFAULT = 60

	def _download(self, url: str, timeout: int = 0) -> list:
		res = []
		thumbnail = None
		yt = YouTube(url)
		if yt and yt.thumbnail_url:
			thumbnail = self.download_thumbnail(yt.thumbnail_url)
		stream = yt.streams.get_highest_resolution()
		if stream:
			local_file = stream.download(
				output_path=self.DOWNLOAD_DIR,
				max_retries=0,
				timeout=timeout,
				skip_existing=False,
				filename_prefix="yt_download_"
			)
			logging.debug("Temp filename: '%s'", local_file)
			res.append({
				"local_media_path": self.rename_local_file(local_file),
				"performer": yt.author,
				"thumb": thumbnail,
				"canonical_name": stream.title,
				"media_type": JobType.VIDEO
			})

		return res

	def download(self, url: str) -> list:
		return self._download_hndlr(self._download, url)