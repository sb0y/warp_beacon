import os
import time
import logging
from mimetypes import guess_extension, guess_type
from urllib.parse import urlparse
import requests
import yt_dlp
from playwright.sync_api import sync_playwright, Page

from warp_beacon.telegram.utils import Utils
from warp_beacon.scraper.utils import ScraperUtils
from warp_beacon.jobs.types import JobType
from warp_beacon.scraper.X.abstract import XAbstract

from warp_beacon.scraper.exceptions import Unavailable

class XScraper(XAbstract):
	DOWNLOAD_DIR = "/tmp"

	def extract_canonical_name(self, media: dict) -> str:
		ret = ""
		try:
			if media.get("description"):
				ret = media["description"]
			elif media.get("title"):
				ret = media["title"]
		except Exception as e:
			logging.warning("Failed to extract canonical media name!")
			logging.exception(e)

		return ret

	def generate_result(self, local_files: list, job_type: JobType, canonical_name: str = "", performer: str = "") -> list:
		res = []
		if local_files:
			if job_type == JobType.COLLECTION:
				chunks = []
				for media_chunk in Utils.chunker(local_files, 10):
					chunk = []
					for media in media_chunk:
						mime_type, _ = guess_type(media)
						chunk.append({
							"local_media_path": self.rename_local_file(media),
							"canonical_name": canonical_name,
							"media_type": JobType.VIDEO if "video" in mime_type else JobType.IMAGE,
							"media_info": {}
						})
					chunks.append(chunk)
					res.append({
						"media_type": JobType.COLLECTION,
						"canonical_name": canonical_name,
						"items": chunks
					})
			else:
				for local_file in local_files:
					res.append({
						"local_media_path": self.rename_local_file(local_file),
						"performer": performer,
						"canonical_name": canonical_name,
						"media_type": job_type
					})
		logging.debug(res)
		return res

	def _download(self, url: str, timeout: int = 60) -> list:
		res = []
		post_text = ""
		pw_proxy = None
		if self.proxy:
			dsn = self.proxy.get("dsn", "")
			if dsn:
				parsed = urlparse(dsn)
				pw_proxy = {
					"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
					"username": parsed.username,
					"password": parsed.password
				}
				logging.info("[X] build proxy: %s", pw_proxy)

		contains_images, contains_videos = False, False
		images, videos = [], []
		with sync_playwright() as p:
			with p.chromium.launch(headless=True) as browser:
				with browser.new_context(proxy=pw_proxy, ignore_https_errors=True) as context:
					page = context.new_page()
					page.goto(url, wait_until="networkidle", timeout=(timeout*1000))
					page.wait_for_selector("article[role='article']", timeout=(timeout*1000))

					contains_videos = self.tweet_contains_video(page)
					contains_images = self.tweet_contains_images(page)

					if contains_images:
						post_text, images = self.download_images(page, timeout)

					if not contains_images and not contains_videos:
						post_text = self.extract_post_text(page)

		if contains_videos:
			media_info, videos = self.download_videos(url, timeout)
			if media_info:
				post_text = self.extract_canonical_name(media_info)

		if not images and not videos:
			if not post_text:
				raise Unavailable("Content unvailable")
			logging.info("[X]: Sending text message")
			res.append({
				"message_text": post_text,
				"media_type": JobType.TEXT
			})
			return res
		
		if len(images) > 1 or len(videos) > 1:
			logging.info("[X]: uploading collection")
			content = images + videos
			res.extend(self.generate_result(content, JobType.COLLECTION, canonical_name=post_text))
		else:
			logging.info("[X]: uploading media")
			for job_type, content in {JobType.IMAGE: images, JobType.VIDEO: videos}.items():
				if content:
					res.extend(self.generate_result(content, job_type, canonical_name=post_text))

		return res

	def download_videos(self, url: str, timeout: int = 60) -> tuple[dict, list[str]]:
		local_files = []
		media_info = {}
		time_name = str(time.time()).replace('.', '_')
		ydl_opts = {
			'socket_timeout': timeout,
			'outtmpl': f'{self.DOWNLOAD_DIR}/x_download_{time_name}_%(id)s.%(ext)s',
			'quiet': False,
			'force_generic_extractor': False,
			#'noplaylist': True,
			'merge_output_format': 'mp4',
			'dump_single_json': False,
			'nocheckcertificate': True,
			'progress_hooks': [self.dlp_on_progress],
		}
		if self.proxy:
			proxy_dsn = self.proxy.get("dsn", "")
			logging.info("[X] Using proxy DSN '%s'", proxy_dsn)
			if proxy_dsn:
				ydl_opts["proxy"] = proxy_dsn

		with yt_dlp.YoutubeDL(ydl_opts) as ydl:
			info = ydl.extract_info(url, download=False)
			media_info = info
			entries = info.get("entries", [info])

			for entry in entries:
				ret = ydl.download([entry['webpage_url']])
				if ret == 0:
					file_path = ydl.prepare_filename(entry)
					if isinstance(file_path, str):
						local_files.append(file_path)
					else:
						local_files.extend(file_path)

		return media_info, local_files

	def adaptive_chunk_size(self, content_length: int) -> int:
		if content_length < 100_000:
			return 2048
		elif content_length < 5_000_000:
			return 8192
		elif content_length < 100_000_000:
			return 32768
		else:
			return 65536

	def get_extension_from_headers(self, response: requests.Response) -> str:
		content_type = response.headers.get("Content-Type", "")
		return guess_extension(content_type) or ".jpg"

	def download_images(self, page: Page, timeout: int) -> tuple[str, list[str]]:
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

		image_urls, post_text = self.extract_image_urls_from_x_post(page, timeout)

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

		return post_text, downloaded_imgs

	def extract_image_urls_from_x_post(self, page: Page, timeout: int) -> tuple[list[str], str]:
		img_urls, post_text = [], ''

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
	
	def extract_post_text(self, page: Page) -> str:
		try:
			text_fragments = []

			# find tweetText containers (in main and quoted)
			containers = page.query_selector_all('div[data-testid="tweetText"]')
			for container in containers:
				fragments = []

				# find <span> and <img alt=...> inside text
				for node in container.query_selector_all("span, img"):
					tag = node.evaluate("node => node.tagName.toLowerCase()")
					if tag == "span":
						value = node.inner_text().strip()
						if value:
							fragments.append(value)
					elif tag == "img":
						# emoji as image
						alt = node.get_attribute("alt")
						if alt:
							fragments.append(alt)

				if fragments:
					text_fragments.append("".join(fragments))

			return "\n\n".join(text_fragments).strip()

		except Exception as e:
			logging.warning("X: [extract_post_text] error", exc_info=e)
		return ""