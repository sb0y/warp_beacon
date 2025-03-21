import logging

from pytubefix.exceptions import AgeRestrictedError

from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract
from warp_beacon.scraper.exceptions import YoutubeLiveError, NotFound, YotubeAgeRestrictedError

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

	def _download(self, url: str, session: bool = True, timeout: int = 0) -> list:
		res = []
		try:
			thumbnail = None
			video_id = self.get_video_id(url)
			if video_id:
				thumbnail = self.download_hndlr(self.download_thumbnail, video_id)
			yt = self.build_yt(url, session=session)

			if self.is_live(yt.initial_data):
				raise YoutubeLiveError("Youtube Live is not supported")

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
	
	def _download_yt_dlp(self, url: str) -> list:
		res = []
		thumbnail = None
		video_id = self.get_video_id(url)
		if video_id:
			thumbnail = self.download_hndlr(self.download_thumbnail, video_id)
		with self.build_yt_dlp() as ydl:
			info = ydl.extract_info(url, download=True)
			local_file = ydl.prepare_filename(info)
			logging.debug("Temp filename: '%s'", local_file)
			res.append({
				"local_media_path": local_file,
				"performer": info.get("uploader", "Unknown"),
				"thumb": thumbnail,
				"canonical_name": info.get("title", ''),
				"media_type": JobType.VIDEO
			})

		return res