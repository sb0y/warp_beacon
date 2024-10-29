import multiprocessing.managers
import os
import json
import re

import multiprocessing

from warp_beacon.jobs import Origin

import logging

class AccountSelector(object):
	accounts = []
	current = None
	current_module_name = None
	accounts_meta_data = None
	session_dir = "/var/warp_beacon"
	manager = None
	account_index = {}

	def __init__(self, manager: multiprocessing.managers.SyncManager, acc_file_path: str) -> None:
		self.manager = manager
		self.accounts_meta_data = self.manager.dict()
		if os.path.exists(acc_file_path):
			with open(acc_file_path, 'r', encoding="utf-8") as f:
				self.accounts = json.loads(f.read())
			if self.accounts:
				self.__init_meta_data()
				#self.load_yt_sessions()
				for acc_type, _ in self.accounts.items():
					self.account_index[acc_type] = self.manager.Value('i', 0)
		else:
			raise ValueError("Accounts file not found")

	def __del__(self) -> None:
		pass

	#def enrich_service_data(self) -> None:
	#	for k, v in self.accounts.items():

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
				self.accounts_meta_data[module_name].insert(index, {"auth_fails": 0, "rate_limits": 0, "cathcha": 0})

	def set_module(self, module_origin: Origin) -> None:
		module_name = 'youtube' if next((s for s in ("yt", "youtube", "youtu_be") if s in module_origin.value), None) else 'instagram'
		self.current_module_name = module_name
		if self.current is None:
			self.current = self.accounts[self.current_module_name][self.account_index[self.current_module_name].value]

	def next(self) -> dict:
		idx = self.account_index[self.current_module_name].value + 1
		if idx > len(self.accounts[self.current_module_name]) - 1:
			idx = 0
		self.current = self.accounts[self.current_module_name][idx]
		self.account_index[self.current_module_name].value = idx
		logging.info("Selected account index is '%d'", idx)
		return self.current
	
	def bump_acc_fail(self, key: str, amount: int = 1) -> int:
		try:
			idx = self.account_index[self.current_module_name].value
			self.accounts_meta_data[idx][key] += amount
			return self.accounts_meta_data[idx][key]
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
	
	def get_meta_data(self) -> dict:
		return self.accounts_meta_data[self.current_module_name][self.account_index[self.current_module_name].value]
	
	def count_service_accounts(self, mod_name: Origin) -> int:
		module_name = 'youtube' if next((s for s in ("yt", "youtube", "youtu_be") if s in mod_name.value), None) else 'instagram'
		if module_name not in self.accounts:
			return 0
		return len(self.accounts[module_name])