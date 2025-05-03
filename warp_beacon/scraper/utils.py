import os
from multiprocessing.managers import Namespace
import random
import uuid
import logging

class Utils(object):
	session_dir = "/var/warp_beacon"

	@staticmethod
	def get_ig_session_id() -> str:
		ig_session_client_id = ""
		try:
			sess_file = f"{Utils.session_dir}/ig_session_client_id"
			if os.path.exists(sess_file):
				with open(sess_file, 'r', encoding="utf-8") as f:
					ig_session_client_id = f.read().strip()
		except Exception as e:
			logging.warning("Failed to read session ig_session_client_id!")
			logging.exception(e)

		if not ig_session_client_id:
			ig_session_client_id = str(uuid.uuid4())

		return ig_session_client_id
	
	@staticmethod
	def save_ig_session_id(ig_session_client_id: str) -> None:
		try:
			with open(f"{Utils.session_dir}/ig_session_client_id", "w+", encoding="utf-8") as f:
				f.write(ig_session_client_id)
		except Exception as e:
			logging.warning("Failed to save session ig_session_client_id!")
			logging.exception(e)
	
	@staticmethod
	def maybe_rotate_ig_client_session(context: Namespace) -> None:
		if random.random() > 0.95:
			context.ig_session_client_id = str(uuid.uuid4())
			logging.info("Rotated client_session_id — simulating app restart")