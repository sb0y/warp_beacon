import logging

from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract
from warp_beacon.scraper.exceptions import NotFound

from warp_beacon.mediainfo.video import VideoInfo

class YoutubeShortsScraper(YoutubeAbstract):
	YT_MAX_RETRIES_DEFAULT = 8
	YT_PAUSE_BEFORE_RETRY_DEFAULT = 3
	YT_TIMEOUT_DEFAULT = 2
	YT_TIMEOUT_INCREMENT_DEFAULT = 60

	def _download(self, url: str, session: bool = True, timeout: int = 0) -> list:
		res = []
		thumbnail = None
		yt = self.build_yt(url, session=session)
		stream = yt.streams.get_highest_resolution()

		if not stream:
			raise NotFound("No suitable video stream found")

		local_file = stream.download(
			output_path=self.DOWNLOAD_DIR,
			max_retries=0,
			timeout=timeout,
			skip_existing=False,
			filename_prefix="yt_download_"
		)

		local_file = self.rename_local_file(local_file)
		vinfo = VideoInfo(local_file)
		thumbnail = self.download_hndlr(self.download_thumbnail, video_id=yt.video_id, crop_center=vinfo.get_demensions())

		logging.debug("Temp filename: '%s'", local_file)
		res.append({
			"local_media_path": local_file,
			"performer": yt.author,
			"thumb": thumbnail,
			"canonical_name": stream.title,
			"media_type": JobType.VIDEO
		})

		return res

	def _download_yt_dlp(self, url: str, timeout: int = 60) -> list:
		res = []
		thumbnail = None
		video_id = self.get_video_id(url)
		if video_id:
			thumbnail = self.download_hndlr(self.download_thumbnail, video_id)
		with self.build_yt_dlp(timeout) as ydl:
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