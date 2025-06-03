import os
import time
import logging
from mimetypes import guess_extension
from urllib.parse import urlparse
import requests
import yt_dlp
from playwright.sync_api import sync_playwright, Page

from warp_beacon.telegram.utils import Utils
from warp_beacon.scraper.utils import ScraperUtils
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

	def get_media_type(self, media_info: dict) -> XMediaType:
		media_type = XMediaType.UNKNOWN
		#logging.info("[X] post info: '%s'", media_info)

		if 'ext' in media_info:
			logging.info("[X] Format: '%s'", media_info['ext'])
		if 'formats' in media_info:
			logging.info("[X] Contains video.")
			media_type = XMediaType.VIDEO
		elif 'thumbnails' in media_info:
			logging.info("[X] contains images.")
			media_type = XMediaType.IMAGE
		else:
			logging.info("[X] No media found.")

		return media_type

	def _download(self, url: str, timeout: int = 60) -> list:
		res = []
		job_type = JobType.UNKNOWN
		time_name = str(time.time()).replace('.', '_')
		ydl_opts = {
			'socket_timeout': timeout,
			'outtmpl': f'{self.DOWNLOAD_DIR}/x_download_{time_name}.%(ext)s',
			'quiet': False,
			'force_generic_extractor': False,
			'noplaylist': True,
			'merge_output_format': 'mp4',
			'dump_single_json': True,
			'nocheckcertificate': True,
			'progress_hooks': [self.dlp_on_progress],
		}

		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			logging.info("[X] Using proxy DSN '%s'", proxy_dsn)
			if proxy_dsn:
				ydl_opts["proxy"] = proxy_dsn

		local_file, media_info, media_type, post_text = "", {}, XMediaType.UNKNOWN, ""
		#tweet_contains_video, tweet_contains_images = False, False

		#with sync_playwright() as p:
		#	with p.chromium.launch(headless=True) as browser:
		#		with browser.new_context(proxy=proxy, ignore_https_errors=True) as context:
		#			page = context.new_page()
		#			page.goto(url, wait_until="networkidle", timeout=(timeout*1000))
		#			tweet_contains_video = self.tweet_contains_video(page)
		#			tweet_contains_images = self.tweet_contains_images(page)

		with yt_dlp.YoutubeDL(ydl_opts) as ydl:
			try:
				media_info = ydl.extract_info(url, download=False)
				media_type = self.get_media_type(media_info)
				if media_type == XMediaType.VIDEO:
					local_file = self.download_video(url, ydl, media_info)
					post_text = self.extract_canonical_name(media_info)
					job_type = JobType.VIDEO
			except yt_dlp.utils.DownloadError as e:
				msg = str(e).lower()
				if "no video could be found in this tweet" in msg:
					logging.warning("[X] yt_dlp failed to extract info. Falling back to image scraping.")
					media_type = XMediaType.IMAGE
				else:
					raise
		
		images = []
		if media_type == XMediaType.IMAGE:
			job_type = JobType.IMAGE
			images, post_text = self.download_images(url, timeout)
			if images:
				if len(images) > 1:
					job_type = JobType.COLLECTION
				else:
					local_file = images[0]

		if job_type == JobType.COLLECTION:
			chunks = []
			for media_chunk in Utils.chunker(images, 10):
				chunk = []
				for media in media_chunk:
					chunk.append({
						"local_media_path": self.rename_local_file(media),
						"canonical_name": post_text,
						"media_type": JobType.IMAGE
					})
				chunks.append(chunk)
			res.append({
				"media_type": JobType.COLLECTION,
				"items": chunks
			})
		else:
			if local_file:
				res.append({
					"local_media_path": self.rename_local_file(local_file),
					"performer": media_info.get("uploader", "Unknown"),
					"canonical_name": post_text,
					"media_type": job_type
				})

		return res

	def adaptive_chunk_size(self, content_length: int) -> int:
		if content_length < 100_000:
			return 2048
		elif content_length < 5_000_000:
			return 8192
		elif content_length < 100_000_000:
			return 32768
		else:
			return 65536

	def download_video(self, url: str, ydl: yt_dlp.YoutubeDL, media_info: dict) -> str:
		local_file = ""
		ydl.download([url])
		local_file = ydl.prepare_filename(media_info)
		logging.debug("Temp filename: '%s'", local_file)
		if local_file:
			local_file = self.rename_local_file(local_file)
		return local_file

	def get_extension_from_headers(self, response: requests.Response) -> str:
		content_type = response.headers.get("Content-Type", "")
		return guess_extension(content_type) or ".jpg"

	def download_images(self, url: str, timeout: int = 60) -> tuple[list[str], str]:
		downloaded_imgs = []
		headers = {
			"User-Agent": ScraperUtils.get_ua(),
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
			"Accept-Language": "en-us,en;q=0.5",
			"Sec-Fetch-Mode": "navigate"
		}
		proxies = None
		if self.proxy:
			proxies = {"https": self.proxy.get("dsn", ""), "http": self.proxy.get("dsn", "")}

		image_urls, post_text = self.extract_image_urls_from_x_post(url, timeout=timeout)

		if not image_urls:
			logging.error("[X] Content images are not found!")
			return downloaded_imgs

		time_name = str(time.time()).replace('.', '_')
		for i, img_url in enumerate(set(image_urls)):
			downloaded = 0
			if "?name=small" in img_url:
				img_url = img_url.replace("?name=small", "?name=orig")
			with requests.get(
				img_url,
				headers=headers,
				timeout=timeout,
				stream=True,
				verify=False,
				proxies=proxies) as request:
				
				request.raise_for_status()

				parsed = urlparse(img_url)
				ext = os.path.splitext(parsed.path)[1]
				if not ext:
					ext = self.get_extension_from_headers(request)
				filename = f"x_download_{time_name}_{i}{ext}"
				filepath = os.path.join(self.DOWNLOAD_DIR, filename)

				content_length = int(request.headers.get("Content-Length", 0))

				with open(filepath, "wb") as f:
					#request.raw.decode_content = True
					chunk_size = self.adaptive_chunk_size(content_length)
					for chunk in request.iter_content(chunk_size=chunk_size):
						if chunk:
							f.write(chunk)
							downloaded += len(chunk)
							self.download_progress(
								total=content_length or None,
								bytes_transferred=downloaded,
								path=filepath
							)
				downloaded_imgs.append(filepath)

		return downloaded_imgs, post_text

	def extract_post_text(self, page: Page) -> str:
		try:
			tweet_texts = []
			# collecting text blocks from post
			containers = page.query_selector_all('div[data-testid="tweetText"]')
			for container in containers:
				try:
					spans = container.query_selector_all("span")
					if spans:
						for span in spans:
							text = span.inner_text().strip()
							if text:
								tweet_texts.append(text)
					else:
						# to span's try container itself
						text = container.inner_text().strip()
						if text:
							tweet_texts.append(text)
				except Exception:
					continue

			return " ".join(tweet_texts).strip()
		except Exception as e:
			logging.warning("Failed to extract tweet text.", exc_info=e)

		return ""

	def extract_image_urls_from_x_post(self, url: str, timeout: int = 60) -> tuple[list[str], str]:
		img_urls, post_text = [], ''

		proxy = None
		if self.proxy:
			dsn = self.proxy.get("dsn", "")
			if dsn:
				parsed = urlparse(dsn)
				proxy = {
					"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
					"username": parsed.username,
					"password": parsed.password
				}
				logging.info("[X] build proxy: %s", proxy)

		with sync_playwright() as p:
			with p.chromium.launch(headless=True) as browser:
				with browser.new_context(proxy=proxy, ignore_https_errors=True) as context:
					page = context.new_page()
					page.goto(url, wait_until="networkidle", timeout=(timeout*1000))

					#page.wait_for_timeout(3000)
					page.wait_for_selector("img[src*='pbs.twimg.com/media']", timeout=(timeout*1000))
					post_text = self.extract_post_text(page)

					image_elements = page.query_selector_all("img")
					image_urls = []

					for img in image_elements:
						src = img.get_attribute("src")
						if src and "pbs.twimg.com/media" in src:
							image_urls.append(src)
					
					img_urls = list(set(image_urls))
		return img_urls, post_text
	
	def get_media_type_from_info_and_dom(self, media_info: dict, page: Page) -> XMediaType:
		is_video = (
			media_info.get("vcodec") != "none" or
			media_info.get("ext") in {"mp4", "mov", "mkv"} or
			any(
				f.get("vcodec") not in (None, "none")
				for f in media_info.get("formats", [])
			)
		)

		try:
			image_elements = page.query_selector_all("img")
			image_urls = [
				img.get_attribute("src")
				for img in image_elements
				if img.get_attribute("src") and "pbs.twimg.com/media" in img.get_attribute("src")
			]
			has_images = bool(image_urls)
		except Exception:
			has_images = False

		if is_video and has_images:
			return XMediaType.MIXED
		elif is_video:
			return XMediaType.VIDEO
		elif has_images:
			return XMediaType.IMAGE
		
		return XMediaType.UNKNOWN
	
	def tweet_contains_video(self, page: Page) -> bool:
		try:
			return bool(
				page.query_selector("article video") or
				page.query_selector("div[data-testid='videoPlayer']") or
				page.query_selector("div[aria-label='Embedded video']")
			)
		except Exception:
			pass
		return False
		
	def tweet_contains_images(self, page: Page) -> bool:
		try:
			image_elements = page.query_selector_all("img")
			image_urls = [
				img.get_attribute("src")
				for img in image_elements
				if img.get_attribute("src") and "pbs.twimg.com/media" in img.get_attribute("src")
			]
			return bool(image_urls)
		except Exception:
			pass
		return False