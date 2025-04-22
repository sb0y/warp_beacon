import time
import os
import logging

import av
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

	def _download(self, url: str, session: bool = True, timeout: int = 60) -> list:
		res = self._download_pytubefix_max_res(url=url, session=session, timeout=timeout)
		if not res:
			res = self._download_pytube_dash(url=url, session=session, timeout=timeout)

		return res
	
	def mux_raw_copy(self, video_path: str, audio_path: str, output_path: str) -> str:
		try:
			with av.open(video_path) as input_video, av.open(audio_path) as input_audio, av.open(output_path, mode='w') as output:
				in_video_stream = input_video.streams.video[0]
				in_audio_stream = input_audio.streams.audio[0]

				video_stream_map = output.add_stream(template=in_video_stream)
				audio_stream_map = output.add_stream(template=in_audio_stream)

				for packet in input_video.demux(in_video_stream):
					if packet.dts is None:
						continue
					packet.stream = video_stream_map
					output.mux(packet)

				for packet in input_audio.demux(in_audio_stream):
					if packet.dts is None:
						continue
					packet.stream = audio_stream_map
					output.mux(packet)
		except Exception as e:
			logging.error("Failed to mux audio and video!")
			logging.exception(e)
			return ''

		return output_path

	def _download_pytubefix_max_res(self, url: str, session: bool = True, timeout: int = 60) -> list:
		res = []
		local_video_file, local_audio_file = '', ''
		try:
			thumbnail = None
			video_id = self.get_video_id(url)
			if video_id:
				thumbnail = self.download_hndlr(self.download_thumbnail, video_id)
			yt = self.build_yt(url, session=session)

			if self.is_live(yt.initial_data):
				raise YoutubeLiveError("Youtube Live is not supported")
			
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

	def _download_pytube_dash(self, url: str, session: bool = True, timeout: int = 60) -> list:
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