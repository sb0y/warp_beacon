import os
import time
import random
import logging
import asyncio
from types import CoroutineType
from typing import Any
from urllib.parse import urlparse
import requests
from warp_beacon.scraper.instagram.instagram import InstagramScraper
from pydub import AudioSegment
import speech_recognition as sr
from playwright.async_api import async_playwright, Page

class CaptchaSolver(object):
	TIMEOUT_STANDARD = 7
	TIMEOUT_SHORT = 1
	TIMEOUT_DETECTION = 0.05
	TEMP_DIR = "/tmp"

	scraper = None
	proxy_config = None

	def __init__(self, scraper: InstagramScraper) -> None:
		self.scraper = scraper
		if self.scraper.proxy:
			dsn = self.scraper.proxy.get("dsn", "")
			self.proxy_config = self.parse_proxy_from_dsn(dsn)

	def parse_proxy_from_dsn(self, dsn: str) -> dict:
		parsed = urlparse(dsn)
		
		proxy_config = {
			"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
		}
		
		if parsed.username and parsed.password:
			proxy_config["username"] = parsed.username
			proxy_config["password"] = parsed.password

		return proxy_config

	async def _patch_page(self, page: CoroutineType[Any, Any, Page]):
		await page.add_init_script("""() => {
			Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
			window.chrome = { runtime: {} };
			Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
			Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
		}""")

	async def solve_audio_captcha(self, page: CoroutineType[Any, Any, Page]) -> None:
		logging.info("Processing audio captcha ..")
		mp3_path = os.path.join(self.TEMP_DIR, f"{random.randrange(1,1000)}.mp3")
		wav_path = os.path.join(self.TEMP_DIR, f"{random.randrange(1,1000)}.wav")
		try:
			await page.click('button[aria-label=\"Get an audio challenge\"]')
			time.sleep(0.3)
			await page.wait_for_selector('audio', timeout=10000)

			audio_src = await page.get_attribute('audio > source', 'src')
			audio_content = requests.get(audio_src, timeout=60).content
			with open(mp3_path, 'wb') as f:
				f.write(audio_content)

			if not os.path.exists(mp3_path):
				logging.error("MP3 file not downloaded!")
				return

			sound = AudioSegment.from_mp3(mp3_path)
			sound.export(wav_path, format='wav')

			recognizer = sr.Recognizer()
			with sr.AudioFile(wav_path) as source:
				audio = recognizer.record(source)

			try:
				text = recognizer.recognize_google(audio)
				logging.info("Detected text '%s'", text)
			except sr.UnknownValueError:
				logging.error("Failed to detect text!")
				text = ''

			if text:
				await page.fill('input[type=\"text\"]', text)
				await page.press('input[type=\"text\"]', 'Enter')
				logging.info("Audio captcha solved!")
		except Exception as e:
			logging.error("Exception in captcha audio solve!")
			logging.exception(e)
		finally:
			if os.path.exists(mp3_path):
				os.unlink(mp3_path)
			if os.path.exists(wav_path):
				os.unlink(wav_path)

	async def solve_challenge(self, challenge_url: str) -> None:
		async with async_playwright() as p:
			browser = None
			try:
				browser = await p.chromium.launch(
					headless=True,
					args=[
						"--no-sandbox",
						"--disable-blink-features=AutomationControlled",
						"--disable-infobars",
						"--disable-dev-shm-usage"
					],
					proxy=self.proxy_config
				)
				context = await browser.new_context(
					viewport={"width": 1280, "height": 800},
					user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
					java_script_enabled=True,
					locale="en-US"
				)

				page = await context.new_page()
				await self._patch_page(page)

				await page.goto(challenge_url)

				# finding iframe with captcha
				frame_element = await page.wait_for_selector('iframe[src*=\"recaptcha\"]')
				frame = await frame_element.content_frame()
				time.sleep(0.1)

				# checkbox click
				checkbox = await frame.wait_for_selector('#recaptcha-anchor', timeout=10000)
				await checkbox.click()

				# waiting for frame with task
				await asyncio.sleep(3)

				# checking if iframe with task exists
				frames = page.frames
				challenge_frame = None
				for f in frames:
					if '/recaptcha/' in f.url and 'bframe' in f.url:
						challenge_frame = f
						break

				if not challenge_frame:
					logging.info("Captcha solved!")
				else:
					await self.solve_audio_captcha(challenge_frame)
			except Exception as e:
				logging.error("Exception in solver!")
				logging.exception(e)

			if browser:
				await asyncio.sleep(10)
				await browser.close()

	def run(self, challenge_url: str) -> None:
		asyncio.run(self.solve_challenge(challenge_url))