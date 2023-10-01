import io
from typing import Optional
import cv2

class VideoInfo(object):
	vid = None

	def __init__(self, filename: str) -> None:
		self.vid = cv2.VideoCapture(filename)
		
	def __del__(self) -> None:
		self.vid.release()

	def get_demensions(self) -> dict:
		res = {"width": None, "height": None}
		if self.vid.isOpened():
			res["width"] = int(self.vid.get(cv2.CAP_PROP_FRAME_WIDTH))
			res["height"] = int(self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT))

		return res

	def get_duration(self) -> int:
		duration_in_seconds = None
		if self.vid.isOpened():
			fps = self.vid.get(cv2.CAP_PROP_FPS)
			total_no_frames = self.vid.get(cv2.CAP_PROP_FRAME_COUNT)
			duration_in_seconds = int(total_no_frames / fps)

		return duration_in_seconds
	
	def get_finfo(self) -> dict:
		res = {}
		res.update(self.get_demensions())
		res["duration"] = self.get_duration()
		return res
	
	def generate_thumbnail(self) -> Optional[io.BytesIO]:
		if self.vid.isOpened():
			count = 4
			success = True
			while success:
				self.vid.set(cv2.CAP_PROP_POS_MSEC,(count*1000))
				success, image = self.vid.read()
				if success:
					success, buffer = cv2.imencode(".png", image)
				if success:
					io_buf = io.BytesIO(buffer)
					io_buf.seek(0)
					return io_buf
				count += 1

		return None
