import os
import time
import random
from urllib.parse import urlparse
import logging
import requests
from mimetypes import guess_extension, guess_type

from playwright.sync_api import sync_playwright#, Page
from playwright_stealth import Stealth

from warp_beacon.scraper.abstract import ScraperAbstract
from warp_beacon.telegram.types import ReportType

class SSSProvider(ScraperAbstract):
	UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64", "Chrome/116.0.5845.96 Safari/537.36")
	provider_url = "https://sssinstagram.com/"
	DOWNLOAD_DIR = "/tmp"
	def __init__(self, account: tuple, proxy: dict=None) -> None:
		super().__init__(account, proxy)
		self._download_progress_threshold = 0
		self.request_headers = {}

	def log_request(self, req) -> None:
		#print("URL:", req.url)
		#print("Headers:", req.headers)
		if req.url and "sssinstagram.com" in req.url:
			for key, value in req.headers.items():
				self.request_headers[key] = value

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
		return guess_extension(content_type) or ".mp4"
	
	def download_progress(self, total: int | None, bytes_transferred: int, path: str) -> None:
		if not total:
			return
		percentage_of_completion = round(bytes_transferred / (total or 1) * 100)
		if percentage_of_completion >= self._download_progress_threshold:
			logging.debug("[Download] ig sss file '%s', %d", path, percentage_of_completion)
			msg = {
				"action": "report_download_status",
				"current": bytes_transferred,
				"total": total or 0,
				"message_id": self.job.placeholder_message_id,
				"chat_id": self.job.chat_id,
				"completed": percentage_of_completion >= 100,
				"report_type": ReportType.PROGRESS
			}
			self.status_pipe.send(msg)
			self._download_progress_threshold += 20

	def _download(self, url: str, timeout: int = 60) -> list:
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
				logging.info("[SSSProvider] build proxy: %s", pw_proxy)
		with Stealth().use_sync(sync_playwright()) as p:
			with p.chromium.launch(headless=True) as browser:
				with browser.new_context(
					proxy=pw_proxy,
					permissions=["clipboard-read", "clipboard-write"],
					ignore_https_errors=True,
					user_agent=random.choice(self.UA),
					locale="en-US",
					viewport={"width": 1280, "height": 800}
				) as context:
					context.set_extra_http_headers({
						"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
						"accept-language": "en-US,en;q=0.9",
						"upgrade-insecure-requests": "1",
						"sec-ch-ua": '"Google Chrome";v="116", "Chromium";v="116", "Not A(Brand";v="24"',
						"sec-ch-ua-mobile": "?0",
						"sec-ch-ua-platform": '"Windows"',
					})
					context.add_init_script(
						"""
						() => {
						Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
						Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
						Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
						Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
						}
						"""
					)
					page = context.new_page()
					page.on("request", self.log_request)
					logging.info("[SSSProvider]: playwright inited")
					page.goto(self.provider_url, wait_until="networkidle", timeout=(timeout*1000))
					input_element = page.wait_for_selector("input.form__input", timeout=(timeout*1000)) 
					logging.info("Page loaded")
					if input_element:
						logging.info("[SSSProvider]: Found input form")
						overlay = page.query_selector("div.fc-dialog.fc-choice-dialog")
						if overlay:
							accept_button = page.query_selector("button.fc-button.fc-cta-consent.fc-primary-button")
							accept_button.click()
							#page.screenshot(path="page.png", full_page=True)
							input_element.click()
							print("here4")
							page.evaluate("text => navigator.clipboard.writeText(text)", url)
							page.keyboard.press("Control+V")
							#submit_button = page.query_selector("input.form__submit")
							#submit_button.click()
							download_a = page.wait_for_selector("a.button__download", timeout=timeout)
							download_link = download_a.get_attribute("href")
							reel_text = page.query_selector("div.output-list__caption").inner_text()
							#download_a.click()
							#print(download_a.get_attribute("href"))
							#headers = context.request
							#requests.get(url=download_a.get_attribute("href"), timeout=timeout)
							session = requests.Session()
							prepared = session.prepare_request(requests.Request("GET", download_link, headers=self.request_headers))
							proxies = None
							if self.proxy:
								proxies = {"https": self.proxy.get("dsn", ""), "http": self.proxy.get("dsn", "")}
							response = session.send(
								prepared,
								stream=True,
								verify=False,
								proxies=proxies,
								timeout=timeout
							)
							response.raise_for_status()

							parsed = urlparse(download_link)
							ext = os.path.splitext(parsed.path)[1]
							if not ext:
								ext = self.get_extension_from_headers(response)
							time_name = str(time.time()).replace('.', '_')
							filename = f"sss_download_{time_name}_{ext}"
							filepath = os.path.join(self.DOWNLOAD_DIR, filename)

							downloaded = 0
							content_length = 0
							try:
								content_length = int(response.headers.get("Content-Length", 0))
							except (TypeError, ValueError):
								logging.info("Content-Length header is missing or invalid.")
							with open(filepath, "wb") as f:
								for chunk in response.iter_content(chunk_size=self.adaptive_chunk_size(content_length)):
									if chunk:
										f.write(chunk)
										downloaded += len(chunk)
										self.download_progress(
											total=content_length or None,
											bytes_transferred=downloaded,
											path=filepath
										)