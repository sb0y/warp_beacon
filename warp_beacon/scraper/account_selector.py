import os
import json
import re

from itertools import cycle

from multiprocessing.managers import BaseManager

from warp_beacon.jobs import Origin

import logging

class AccountSelector(BaseManager):
	accounts = []
	acc_pool = None
	current = None
	current_module_name = None
	index = 0
	accounts_meta_data = {}
	session_dir = "/var/warp_beacon"

	def __init__(self, acc_file_path: str) -> None:
		if os.path.exists(acc_file_path):
			with open(acc_file_path, 'r', encoding="utf-8") as f:
				self.accounts = json.loads(f.read())
			if self.accounts:
				self.__init_meta_data()
				self.load_yt_sessions()
		else:
			raise ValueError("Accounts file not found")
		
		super().__init__()

	def __del__(self) -> None:
		pass

	#def enrich_service_data(self) -> None:
	#	for k, v in self.accounts.items():

	def load_yt_sessions(self) -> None:
		self.accounts["youtube"] = []
		for f in os.listdir(self.session_dir):
			if "yt_session" in f and ".json" in f:
				match = re.search('\d+', f)
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
				self.accounts_meta_data[module_name].insert(index, {"auth_fails": 0, "rate_limits": 0})

	def set_module(self, module_origin: Origin) -> None:
		module_name = 'youtube' if next((s for s in ("yt", "youtube", "youtu_be") if s in module_origin.value), None) else 'instagram'
		self.current_module_name = module_name
		self.acc_pool = cycle(self.accounts[module_name])
		self.current = next(self.acc_pool)
		self.index = self.accounts[module_name].index(self.current)

	def next(self) -> dict:
		self.current = next(self.acc_pool)
		self.index = self.accounts[self.current_module_name].index(self.current)
		logging.info("Next account index is '%d'", self.index)
		return self.current
	
	def bump_acc_fail(self, key: str, amount: int = 1) -> int:
		self.accounts_meta_data[self.index][key] += amount
		return self.accounts_meta_data[self.index][key]

	def how_much(self, key: str) -> int:
		return self.accounts_meta_data[self.current_module_name][self.index][key]
	
	def get_current(self) -> tuple:
		return (self.index, self.current)
	
	def get_meta_data(self) -> dict:
		return self.accounts_meta_data[self.current_module_name][self.index]
	
	def count_service_accounts(self, mod_name: Origin) -> int:
		module_name = 'youtube' if next((s for s in ("yt", "youtube", "youtu_be") if s in mod_name.value), None) else 'instagram'
		if module_name not in self.accounts_meta_data:
			return 0
		return len(self.accounts_meta_data[module_name])