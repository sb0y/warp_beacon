import logging
import multiprocessing
import multiprocessing.connection
import os
import socket
import pathlib
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Union

from PIL import Image
from pillow_heif import register_heif_opener

import requests.packages.urllib3.util.connection as urllib3_cn

if TYPE_CHECKING:
	from multiprocessing.synchronize import Event as EventType

from warp_beacon.scraper.account_selector import AccountSelector

class ScraperAbstract(ABC):
	def __init__(self, account: tuple, proxy: dict = None) -> None:
		self.original_gai_family = None
		self.send_message_to_admin_func: Callable = lambda: None
		self.request_yt_auth: Callable = lambda: None
		self.status_pipe: multiprocessing.connection.Connection = None
		self.yt_validate_event: EventType = None
		self.auth_event = None
		self.acc_selector: AccountSelector = None
		self.account = None
		self.account_index = 0
		self.proxy = None
		self.job = None
		self._gai_lock = multiprocessing.Lock()
		self.account_index = account[0]
		self.account = account[1]
		self.proxy = proxy
		#if self.account.get("force_ipv6", False):
		#	self.force_ipv6()

	#def __del__(self) -> None:
	#	if self.account.get("force_ipv6", False):
	#		self.restore_gai()

	@abstractmethod
	def download(self, url: str) -> bool:
		raise NotImplementedError

	@abstractmethod
	def download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
		raise NotImplementedError

	@staticmethod
	def convert_webp_to_png(src_file: str) -> str:
		try:
			if os.path.exists(src_file):
				path_info = pathlib.Path(src_file)
				old_filename = path_info.stem
				new_filename = f"{old_filename}_converted.png"
				new_filepath = f"{os.path.dirname(src_file)}/{new_filename}"
				with Image.open(src_file).convert('RGB') as img:
					img.save(new_filepath, 'png')
				os.unlink(src_file)
				return new_filepath
		except Exception as e:
			logging.error("Failed to convert webp file to png!")
			logging.exception(e)

		return ''

	@staticmethod
	def convert_heic_to_png(src_file: str) -> str:
		try:
			if os.path.exists(src_file):
				register_heif_opener()
				path_info = pathlib.Path(src_file)
				old_filename = path_info.stem
				new_filename = f"{old_filename}_converted.png"
				new_filepath = f"{os.path.dirname(src_file)}/{new_filename}"
				with Image.open(src_file).convert('RGB') as img:
					img.save(new_filepath, 'png')
				os.unlink(src_file)
				return new_filepath
		except Exception as e:
			logging.error("Failed to convert webp file to png!")
			logging.exception(e)

		return ''
	
	def rename_local_file(self, filename: str) -> str:
		if not os.path.exists(filename):
			raise NameError("No file provided")
		path_info = pathlib.Path(filename)
		ext = path_info.suffix
		#old_filename = path_info.stem
		time_name = str(time.time()).replace('.', '_')
		new_filename = f"{time_name}{ext}"
		new_filepath = f"{os.path.dirname(filename)}/{new_filename}"

		os.rename(filename, new_filepath)

		return new_filepath

	def force_ipv6(self) -> None:
		def allowed_gai_family():
			"""
			https://github.com/shazow/urllib3/blob/master/urllib3/util/connection.py
			"""
			family = socket.AF_INET
			if urllib3_cn.HAS_IPV6:
				family = socket.AF_INET6 # force ipv6 only if it is available
			return family
		with self._gai_lock:
			if self.original_gai_family is None:
				self.original_gai_family = urllib3_cn.allowed_gai_family
			logging.info("Forcing IPv6 ...")
			urllib3_cn.allowed_gai_family = allowed_gai_family

	def restore_gai(self) -> None:
		return
		with self._gai_lock:
			if self.original_gai_family:
				logging.info("Restoring normal IP stack ...")
				urllib3_cn.allowed_gai_family = self.original_gai_family
				self.original_gai_family = None