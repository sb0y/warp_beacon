import time
import os
import io
from typing import Optional
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

	def _download(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		res = self._download_pytubefix_max_res(url=url, session=session, thumbnail=thumbnail, timeout=timeout)
		if not res:
			res = self._download_pytube_dash(url=url, session=session, thumbnail=thumbnail, timeout=timeout)

		return res

	def _download_pytubefix_max_res(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		res = []
		local_video_file, local_audio_file = '', ''
		try:
			yt = self.build_yt(url, session=session)

			if self.is_live(yt.initial_data):
				raise YoutubeLiveError("Youtube Live is not supported")
			
			video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc().first()
			audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()
			size_in_bytes = video_stream.filesize + audio_stream.filesize
			if size_in_bytes > 2147483648: # 2 GiB
				video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True, res='720p').order_by('resolution').desc().first()

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

	def _download_pytube_dash(self, url: str, session: bool = True, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		res = []
		try:
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
	
	def _download_yt_dlp(self, url: str, thumbnail: Optional[io.BytesIO] = None, timeout: int = 60) -> list:
		res = []
		with self.build_yt_dlp(timeout) as ydl:
			info = ydl.extract_info(url, download=False)
			formats = info.get('formats', [])

			dl_format = {}
			for f in sorted(formats, key=lambda x: (x.get('height', 0) or 0), reverse=True):
				logging.info("Format: %s, ext=%s, height=%s, acodec=%s, vcodec=%s",
					f.get('format_id'), f.get('ext'), f.get('height'),
					f.get('acodec'), f.get('vcodec'))
				if f.get('vcodec', '') != 'none' and f.get('acodec', '') != 'none' and f.get('ext', '') == 'mp4':
					dl_format = f
					break
		
			filesize = dl_format.get('filesize', 0) or dl_format.get('filesize_approx', 0)
			logging.info("[yt_dlp] File size '%d'", filesize)
			if filesize:
				if filesize > 2147483648: # 2 GiB
					logging.warning("Max resolution exceeding TG limits")
					for f in sorted(formats, key=lambda x: (x.get('height', 0) or 0), reverse=True):
						if (f.get('vcodec', '') != 'none' and f.get('acodec', '') != 'none'
								and (f.get('height', 0) or 0) <= 720 and f.get('ext', '') == 'mp4'):
							alt_filesize = f.get('filesize', 0) or f.get('filesize_approx', 0)
							if alt_filesize: #and alt_filesize <= max_size_bytes:
								dl_format = f
								break
			else:
				logging.warning("Unknown filesize!")
			if not dl_format:
				for f in sorted(formats, key=lambda x: x.get('height', 0), reverse=True):
					if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
						dl_format = f
						break
			ydl.params['format'] = dl_format['format_id']
			ydl.download([url])
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
