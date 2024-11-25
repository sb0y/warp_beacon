from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract
from warp_beacon.scraper.exceptions import NotFound, FileTooBig

import logging

class YoutubeMusicScraper(YoutubeAbstract):
	YT_MAX_RETRIES_DEFAULT = 6
	YT_PAUSE_BEFORE_RETRY_DEFAULT = 3
	YT_TIMEOUT_DEFAULT = 2
	YT_TIMEOUT_INCREMENT_DEFAULT = 60

	def _download(self, url: str, timeout: int = 0) -> list:
		res = []
		thumbnail = None
		yt = self.build_yt(url)

		if yt:
			thumbnail = self._download_hndlr(self.download_thumbnail, yt.video_id)
		
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
			"canonical_name": stream.title,
			"media_type": JobType.AUDIO
		})

		return res

	def download(self, url: str) -> list:
		return self._download_hndlr(self._download, url)
