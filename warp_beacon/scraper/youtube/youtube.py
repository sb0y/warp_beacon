from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract
from warp_beacon.scraper.exceptions import YoutubeLiveError, NotFound, YotubeAgeRestrictedError

from pytubefix.exceptions import AgeRestrictedError

import logging

class YoutubeScraper(YoutubeAbstract):
	YT_MAX_RETRIES_DEFAULT = 8
	YT_PAUSE_BEFORE_RETRY_DEFAULT = 3
	YT_TIMEOUT_DEFAULT = 2
	YT_TIMEOUT_INCREMENT_DEFAULT = 60

	def is_live(self, data: dict) -> bool:
		'''
		x.contents.twoColumnWatchNextResults.results.results.contents[0].videoPrimaryInfoRenderer.viewCount.videoViewCountRenderer.isLive
		'''
		try:
			contents = data.get("contents", {}).get("twoColumnWatchNextResults", {}).get("results", {}).get("results", {}).get("contents", [])
			for i in contents:
				video_view_count_renderer = i.get("videoPrimaryInfoRenderer", {}).get("viewCount", {}).get("videoViewCountRenderer", {})
				if video_view_count_renderer:
					return video_view_count_renderer.get("isLive", False)
		except Exception as e:
			logging.warning("Failed to check if stream is live!")
			logging.exception(e)

		return False

	def _download(self, url: str, timeout: int = 0) -> list:
		res = []
		try:
			thumbnail = None
			yt = self.build_yt(url)

			if self.is_live(yt.initial_data):
				raise YoutubeLiveError("Youtube Live is not supported")

			if yt:
				thumbnail = self._download_hndlr(self.download_thumbnail, yt.video_id)

			stream = yt.streams.get_highest_resolution()

			if not stream:
				raise NotFound("No suitable video stream found")

			logging.info("Starting download ...")

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
		except AgeRestrictedError as e:
			raise YotubeAgeRestrictedError("Youtube Age Restricted error")

		return res