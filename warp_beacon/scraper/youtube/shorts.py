import os
import io
from typing import Optional
import time

import logging

from pytubefix.exceptions import AgeRestrictedError

from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.youtube.abstract import YoutubeAbstract

from warp_beacon.scraper.exceptions import NotFound, YotubeAgeRestrictedError

class YoutubeShortsScraper(YoutubeAbstract):
	YT_MAX_RETRIES_DEFAULT = 8
	YT_PAUSE_BEFORE_RETRY_DEFAULT = 3
	YT_TIMEOUT_DEFAULT = 2
	YT_TIMEOUT_INCREMENT_DEFAULT = 60

	def _download(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		res = self._download_pytubefix_max_res(url=url, session=session, thumbnail=thumbnail, timeout=timeout)
		if not res:
			res = self._download_pytube_dash(url=url, session=session, thumbnail=thumbnail, timeout=timeout)

		return res

	def _download_pytube_dash(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 0) -> list:
		res = []
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

		logging.debug("Temp filename: '%s'", local_file)
		res.append({
			"local_media_path": local_file,
			"performer": yt.author,
			"thumb": thumbnail,
			"canonical_name": stream.title,
			"media_type": JobType.VIDEO
		})

		return res

	def _download_yt_dlp(self, url: str, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
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
				"media_type": JobType.VIDEO
			})

		return res
	
	def _download_pytubefix_max_res(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		res = []
		local_video_file, local_audio_file = '', ''
		try:
			yt = self.build_yt(url, session=session)
			
			video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc().first()
			audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()

			local_video_file = video_stream.download(
				output_path=self.DOWNLOAD_DIR,
				max_retries=3,
				timeout=timeout,
				skip_existing=False,
				filename_prefix="yt_download_video_"
			)
			local_video_file = self.rename_local_file(local_video_file)
			logging.debug("Temp video filename: '%s'", local_video_file)
			local_audio_file = audio_stream.download(
				output_path=self.DOWNLOAD_DIR,
				max_retries=3,
				timeout=timeout,
				skip_existing=False,
				filename_prefix="yt_download_audio_"
			)
			local_audio_file = self.rename_local_file(local_audio_file)
			logging.debug("Temp audio filename: '%s'", local_audio_file)

			muxed_video = self.mux_raw_copy(
				video_path=local_video_file,
				audio_path=local_audio_file,
				output_path=f"{self.DOWNLOAD_DIR}/yt_muxed_video_{int(time.time())}.mp4")
			if muxed_video:
				muxed_video = self.rename_local_file(muxed_video)
				logging.debug("Temp muxed filename: '%s'", muxed_video)

				res.append({
					"local_media_path": muxed_video,
					"performer": yt.author,
					"thumb": thumbnail,
					"canonical_name": yt.title,
					"media_type": JobType.VIDEO
				})
		except AgeRestrictedError as e:
			raise YotubeAgeRestrictedError("Youtube Age Restricted error")
		finally:
			if os.path.exists(local_video_file):
				os.unlink(local_video_file)
			if os.path.exists(local_audio_file):
				os.unlink(local_audio_file)
		
		return res