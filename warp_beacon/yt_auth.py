import os
import time

import logging

import json
import requests

class YtAuth(object):
	TV_CLIENT_ID = "861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com"
	TV_CLIENT_SECRET = "SboVhoG9s0rNafixCSGGKXAT"
	YT_SESSION_FILE_TPL = '/var/warp_beacon/yt_session_%d.json'

	process_start_time = 0
	account_index = 0
	yt_session_file = ""

	def __init__(self, account_index: int) -> None:
		self.account_index = account_index
		self.yt_session_file = self.YT_SESSION_FILE_TPL % account_index

	def fetch_token(self) -> dict:
		result = {"user_code": "", "device_code": "", "verification_url": ""}
		http_code = 0
		response_text = ''
		try:
			logging.info("Fetching YT token ...")
			self.process_start_time = 0
			# Subtracting 30 seconds is arbitrary to avoid potential time discrepencies
			self.process_start_time = int(time.time() - 30)
			data = {
				'client_id': self.TV_CLIENT_ID,
				'scope': 'https://www.googleapis.com/auth/youtube'
			}
			response = requests.post(
				url='https://oauth2.googleapis.com/device/code',
				headers={
					"User-Agent": "Mozilla/5.0",
					"accept-language": "en-US,en",
					"Content-Type": "application/json"
				},
				json=data,
				timeout=int(os.environ.get("YT_TIMEOUT", "30"))
			)

			http_code = response.status_code
			response_text = response.text

			if http_code != 200:
				logging.error("Invalid YT HTTP code: '%d'", http_code)
				logging.info("Request dump: '%s'", str(response.__dict__))
			else:
				response_data = response.json()
				result["verification_url"] = response_data['verification_url']
				result["user_code"] = response_data['user_code']
				result["device_code"] = response_data['device_code']
				logging.info("Fetched YT url '%s' and input code '%s'", result["verification_url"], result['user_code'])
		except Exception as e:
			logging.error("Youtube authorization failed!")
			logging.exception(e)

		if http_code != 200:
			raise ValueError(f"Youtube HTTP response code is {http_code}: {response_text}")

		return result

	def confirm_token(self, device_code: str) -> dict:
		response_data = {}
		http_code = 0
		response_text = ''
		try:
			logging.info("Confirming YT auth token ...")
			self.process_start_time = int(time.time()) - self.process_start_time - 20
			data = {
				'client_id': self.TV_CLIENT_ID,
				'client_secret': self.TV_CLIENT_SECRET,
				'device_code': device_code,
				'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
			}
			response = requests.post(
				url='https://oauth2.googleapis.com/token',
				headers={
					"User-Agent": "Mozilla/5.0",
					"accept-language": "en-US,en",
					"Content-Type": "application/json"
				},
				json=data,
				timeout=int(os.environ.get("YT_TIMEOUT", "30"))
			)

			http_code = response.status_code
			response_text = response.text

			if http_code != 200:
				logging.error("Invalid YT HTTP code: '%d'", http_code)
				logging.info("Request dump: '%s'", str(response.__dict__))
			else:
				response_data = response.json()
				response_data["expires"] = self.process_start_time + int(response_data["expires_in"])
		except Exception as e:
			logging.error("Failed to confirm token!")
			logging.exception(e)

		if http_code != 200:
			raise ValueError(f"Youtube HTTP response code is {http_code}: {response_text}")

		return response_data

	def refresh_token(self, refresh_token: str) -> dict:
		response_data = {}
		http_code = 0
		response_text = ''
		try:
			logging.info("Refreshing YT token ...")
			start_time = int(time.time() - 30)
			data = {
				'client_id': self.TV_CLIENT_ID,
				'client_secret': self.TV_CLIENT_SECRET,
				'grant_type': 'refresh_token',
				'refresh_token': refresh_token
			}
			response = requests.post(
				url='https://oauth2.googleapis.com/token',
				headers={
					"User-Agent": "Mozilla/5.0",
					"accept-language": "en-US,en",
					"Content-Type": "application/json"
				},
				json=data,
				timeout=int(os.environ.get("YT_TIMEOUT", "30"))
			)

			http_code = response.status_code
			response_text = response.text

			if http_code != 200:
				logging.error("Invalid YT HTTP code: '%d'", http_code)
				logging.info("Request dump: '%s'", str(response.__dict__))
			else:
				response_data = response.json()
				response_data["expires"] = start_time + int(response_data["expires_in"])
		except Exception as e:
			logging.error("Failed to refresh YT token")
			logging.exception(e)

		if http_code != 200:
			raise ValueError(f"Youtube HTTP response code is {http_code}: {response_text}")
		
		return response_data

	def safe_write_session(self, token_data: dict) -> bool:
		try:
			tmp_filename = f"{self.yt_session_file}~"
			
			if os.path.exists(tmp_filename):
				os.unlink(tmp_filename)
			
			with open(tmp_filename, "w+", encoding="utf-8") as f:
				f.write(json.dumps(token_data))
			
			if os.path.exists(tmp_filename):
				if os.path.exists(self.yt_session_file):
					os.unlink(self.yt_session_file)
				os.rename(src=tmp_filename, dst=self.yt_session_file)
			return True
		except Exception as e:
			logging.error("Failed to write token!")
			logging.exception(e)

		return False
	
	def store_device_code(self, device_code: str) -> bool:
		try:
			device_code_file = f"/tmp/yt_device_code_acc_{self.account_index}"
			logging.info("Storing device code in file '%s'", device_code_file)
			with open(device_code_file, "w+", encoding="utf-8") as f:
				f.write(device_code.strip())
		except Exception as e:
			logging.error("Failed to store device code!")
			logging.exception(e)
			return False

		return True
	
	def load_device_code(self) -> str:
		device_code = ''
		try:
			device_code_file = f"/tmp/yt_device_code_acc_{self.account_index}"
			logging.info("Loading device code from file '%s'", device_code_file)
			with open(device_code_file, 'r', encoding="utf-8") as f:
				device_code = f.read().strip()
			os.unlink(device_code_file)
		except Exception as e:
			logging.error("Failed to load device code for account #%d", self.account_index)
			logging.exception(e)

		return device_code