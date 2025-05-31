import time
import logging
import yt_dlp

from warp_beacon.scraper.X.types import XMediaType
from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.X.abstract import XAbstract

class XScraper(XAbstract):
	DOWNLOAD_DIR = "/tmp"

	def extract_canonical_name(self, media: dict) -> str:
		ret = ""
		try:
			if media.get("title", None):
				ret = media["title"]
			if media.get("description", ""):
				ret += "\n" + media["description"]
		except Exception as e:
			logging.warning("Failed to extract canonical media name!")
			logging.exception(e)

		return ret

	def _download(self, url: str, media_info: dict, media_type: XMediaType = XMediaType.UNKNOWN, timeout: int = 60) -> list:
		res = []
		if media_type == XMediaType.VIDEO:
			time_name = str(time.time()).replace('.', '_')
			ydl_opts = {
				'socket_timeout': timeout,
				'outtmpl': f'{self.DOWNLOAD_DIR}/x_download_{time_name}.%(ext)s',
				'quiet': False,
				'noplaylist': True,
				'merge_output_format': 'mp4',
			}

			local_file = ""
			with yt_dlp.YoutubeDL(ydl_opts) as ydl:
				local_file = self.rename_local_file(ydl.download([url]))
			logging.debug("Temp filename: '%s'", local_file)
			res.append({
				"local_media_path": local_file,
				"performer": media_info.get("uploader", "Unknown"),
				'progress_hooks': [self.dlp_on_progress],
				#"thumb": thumbnail,
				"canonical_name": self.extract_canonical_name(media_info),
				"media_type": JobType.VIDEO
			})
		else:
			logging.info("Unknown media type: '%s'", media_type.value)

		return res