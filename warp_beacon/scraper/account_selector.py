import os
import time
import random
import json
import re
import uuid
from typing import Optional, List
from itertools import cycle

import logging

import multiprocessing
import multiprocessing.managers

from warp_beacon.jobs import Origin

class AccountSelector(object):
	accounts = None
	proxies = None
	current = None
	current_module_name = None
	accounts_meta_data = None
	session_dir = "/var/warp_beacon"
	manager = None
	account_index = None
	current_proxy = None
	ig_request_count = None
	ig_accounts_session_id = None
	lock = None

	def __init__(self, manager: multiprocessing.managers.SyncManager, acc_file_path: str, proxy_file_path: str=None) -> None:
		self.accounts = []
		self.proxies = []
		self.account_index = {}
		self.manager = manager
		self.lock = self.manager.Lock()
		self.ig_accounts_session_id = self.manager.dict()
		self.load_ig_sessions_id()
		self.accounts_meta_data = self.manager.dict()
		if os.path.exists(acc_file_path):
			with open(acc_file_path, 'r', encoding="utf-8") as f:
				self.accounts = json.loads(f.read())
			if self.accounts:
				self.ig_request_count = self.manager.Value('i', 0)
				self.__init_meta_data()
				#self.load_yt_sessions()
				for acc_type, _ in self.accounts.items():
					self.account_index[acc_type] = self.manager.Value('i', 0)
			if proxy_file_path:
				with open(proxy_file_path, 'r', encoding="utf-8") as f:
					self.proxies = json.loads(f.read())

			self.load_ig_request_count()
		else:
			raise ValueError("Accounts file not found")

	def save_state(self) -> None:
		self.save_ig_request_count()
		self.save_ig_sessions_id()

	def save_ig_sessions_id(self) -> None:
		try:
			with self.lock:
				sessions = dict(self.ig_accounts_session_id)
				logging.info("Saving sessions: %s", sessions)
				with open(f"{self.session_dir}/ig_sessions_client_id.json", "w+", encoding="utf-8") as f:
					json.dump(sessions, f, indent=2)
		except Exception as e:
			logging.warning("Failed to save session ig_session_client_id!")
			logging.exception(e)

	def load_ig_sessions_id(self) -> None:
		try:
			sess_file = f"{self.session_dir}/ig_sessions_client_id.json"
			if os.path.exists(sess_file):
				data = None
				with open(sess_file, 'r', encoding="utf-8") as f:
					data = json.loads(f.read())
				if data and isinstance(data, dict):
					for k, v in data.items():
						self.ig_accounts_session_id[int(k)] = v
		except Exception as e:
			logging.warning("Failed to read session ig_session_client_id!")
			logging.exception(e)

	def save_ig_request_count(self) -> None:
		try:
			state = {"ig_count": self.ig_request_count.value}
			with open(f"{self.session_dir}/ig_request_counter.json", "w+", encoding="utf-8") as f:
				f.write(json.dumps(state))
		except Exception as e:
			logging.error("Failed to save accounts states!")
			logging.exception(e)

	def load_ig_request_count(self) -> None:
		try:
			state = {}
			filepath = f"{self.session_dir}/ig_request_counter.json"
			if os.path.exists(filepath):
				with open(f"{self.session_dir}/ig_request_counter.json", "r", encoding="utf-8") as f:
					state = json.loads(f.read())
				if state:
					self.ig_request_count.value = int(state.get("ig_count", 0))
		except Exception as e:
			logging.error("Failed to save accounts states!")
			logging.exception(e)

	def get_current_proxy(self) -> Optional[dict]:
		return self.current_proxy
	
	def get_last_proxy(self) -> Optional[dict]:
		return self.accounts_meta_data.get("last_proxy", None)

	def get_proxy_list(self, ipv4: bool = False) -> List[dict]:
		matched_proxy = []
		try:
			acc_id, acc_data = self.get_current()
			current_acc_pid = acc_data.get("proxy_id", "").strip()
			for proxy in self.proxies:
				if ipv4:
					if proxy.get("ip_version", '') not in ("v4", "both"):
						continue
				pid = proxy.get("id", "").strip()
				if pid and current_acc_pid and pid == current_acc_pid:
					if "override_force_ipv6" in proxy:
						self.accounts[self.current_module_name][acc_id]["force_ipv6"] = proxy.get("override_force_ipv6", False)
					logging.info("Account proxy matched '%s'", proxy)
					matched_proxy.append(proxy)
		except Exception as e:
			logging.warning("Failed to form proxy list!")
			logging.exception(e)

		return matched_proxy

	def get_random_account_proxy(self, ipv4: bool = False) -> Optional[dict]:
		if self.proxies:
			try:
				matched_proxy = self.get_proxy_list(ipv4)
				if matched_proxy:
					if len(matched_proxy) > 1:
						random.seed(random.seed(time.time_ns() ^ int.from_bytes(os.urandom(len(matched_proxy)), "big")))
						# ensure new proxy in case if previous account required captcha
						last_proxy = self.get_last_proxy()
						if last_proxy and last_proxy in matched_proxy:
							matched_proxy.remove(last_proxy)
					prox_choice = random.choice(matched_proxy)
					# saving chosen proxy for history
					self.accounts_meta_data["last_proxy"] = prox_choice
					self.current_proxy = prox_choice
					logging.info("Chosen proxy: '%s'", prox_choice)
					return prox_choice
			except Exception as e:
				logging.warning("Error on selecting account proxy!")
				logging.exception(e)
		return None
	
	def next_proxy(self) -> Optional[dict]:
		if not self.proxies:
			return None
		proxy = None
		try:
			matched_proxies = self.get_proxy_list()
			if matched_proxies:
				lit = cycle(matched_proxies)
				proxy = next(lit)
				last_proxy = self.get_last_proxy()
				if last_proxy and proxy.get("dsn", "") == last_proxy.get("dsn", ""):
					proxy = next(lit)
				self.current_proxy = proxy
				self.accounts_meta_data["last_proxy"] = proxy
		except Exception as e:
			logging.warning("Error on selection next proxy!")
			logging.exception(e)

		return proxy

	def load_yt_sessions(self) -> None:
		if "youtube" not in self.accounts:
			self.accounts["youtube"] = []
		for f in os.listdir(self.session_dir):
			if "yt_session" in f and ".json" in f:
				match = re.search(r'\d+', f)
				index = 0
				if match:
					index = int(match.group(0))
				self.accounts["youtube"].insert(index, {"session_file": "%s/%s" % (self.session_dir, f), "index": index})
		if not self.accounts["youtube"]:
			self.accounts["youtube"].append({"session_file": "%s/yt_session_0.json" % self.session_dir, "index": 0})

	def __init_meta_data(self) -> None:
		for module_name, lst in self.accounts.items():
			if module_name not in self.accounts_meta_data:
				self.accounts_meta_data[module_name] = []
			for index, _ in enumerate(lst):
				self.accounts_meta_data[module_name].insert(index, {"auth_fails": 0, "rate_limits": 0, "captcha": 0})

	def get_module_name(self, module_origin: Origin) -> str:
		module_name = 'youtube' if next((s for s in ("yt", "youtube", "youtu_be") if s in module_origin.value), None) else 'instagram'
		return module_name

	def set_module(self, module_origin: Origin) -> None:
		module_name = self.get_module_name(module_origin)
		self.current_module_name = module_name
		if self.current is None:
			idx = self.account_index[self.current_module_name].value
			self.current = self.accounts[self.current_module_name][idx]
			if not self.current.get("enabled", True):
				logging.info("Account '%d' is disabled. Probing next ...", idx)
				self.next()
		ipv4 = False
		if module_origin is Origin.X:
			ipv4 = True
		self.current_proxy = self.get_random_account_proxy(ipv4)

	def next(self) -> dict:
		idx = self.account_index[self.current_module_name].value
		idx += 1
		if idx >= len(self.accounts[self.current_module_name]):
			idx = 0
		self.account_index[self.current_module_name].value = idx
		self.current = self.accounts[self.current_module_name][idx]
		if not self.current.get("enabled", True):
			logging.info("Account '%d' is disabled. Probing next ...", idx)
			return self.next()
		logging.info("Selected account index is '%d'", idx)
		return self.current

	def bump_acc_fail(self, key: str, amount: int = 1) -> int:
		try:
			idx = self.account_index[self.current_module_name].value
			meta_list = self.accounts_meta_data[self.current_module_name]
			if idx >= len(meta_list):
				logging.warning("Index '%d' out of range for module '%s' with length '%d'", idx, self.current_module_name, len(meta_list))
				return 0
			self.accounts_meta_data[self.current_module_name][idx][key] += amount
			return meta_list[idx][key]
		except Exception as e:
			logging.warning("Failed to record fail stats")
			logging.exception(e)
		return 0

	def how_much(self, key: str) -> int:
		idx = self.account_index[self.current_module_name].value
		return self.accounts_meta_data[self.current_module_name][idx][key]

	def get_current(self) -> tuple:
		idx = self.account_index[self.current_module_name].value
		return (idx, self.accounts[self.current_module_name][idx])
	
	def get_current_for_module(self, module_origin: Origin) -> tuple:
		module_name = self.get_module_name(module_origin)
		idx = self.account_index[module_name].value
		return (idx, self.accounts[module_name][idx])

	def get_meta_data(self) -> dict:
		idx = self.account_index[self.current_module_name].value# - 1
		return self.accounts_meta_data[self.current_module_name][idx]

	def count_service_accounts(self, mod_name: Origin) -> int:
		module_name = 'youtube' if next((s for s in ("yt", "youtube", "youtu_be") if s in mod_name.value), None) else 'instagram'
		if module_name not in self.accounts:
			return 0
		return len(self.accounts[module_name])
	
	def inc_ig_request_count(self, amount: int = 1) -> None:
		self.ig_request_count.value += int(amount)

	def reset_ig_request_count(self) -> None:
		self.ig_request_count.value = 0

	def get_ig_request_count(self) -> int:
		return int(self.ig_request_count.value)
	
	def get_ig_session_id(self) -> str:
		with self.lock:
			idx = int(self.account_index[self.current_module_name].value)
			if idx not in self.ig_accounts_session_id:
				self.ig_accounts_session_id[idx] = str(uuid.uuid4())
			#else:
				#if random.random() > 0.95:
				#	self.ig_accounts_session_id[idx] = str(uuid.uuid4())
				#	logging.info("Rotated client_session_id — simulating app restart")
			return self.ig_accounts_session_id[idx]
		
	def generate_new_session_id(self) -> str:
		with self.lock:
			idx = self.account_index[self.current_module_name].value
			session_id = str(uuid.uuid4())
			self.ig_accounts_session_id[idx] = session_id
			return session_id