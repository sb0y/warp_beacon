import io, os
from typing import Optional
import cv2

class VideoInfo(object):
	vid = None
	# need for filesize
	filename = ""

	def __init__(self, filename: str) -> None:
		self.vid = cv2.VideoCapture(filename)
		self.filename = filename
		
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
	
	def get_filesize(self) -> float:
		size = os.path.getsize(self.filename)
		return round(size/(pow(1024,2)), 2)
	
	def get_finfo(self, except_info: tuple=()) -> dict:
		res = {}
		res.update(self.get_demensions())
		if "duration" not in except_info:
			res["duration"] = self.get_duration()
		if "filesize" not in except_info:
			res["filesize"] = self.get_filesize()
		return res
	
	def shrink_image_to_fit(self, img):
		height, width = img.shape[:2]
		max_height = 320
		max_width = 320

		# only shrink if img is bigger than required
		if max_height < height or max_width < width:
			# get scaling factor
			scaling_factor = max_height / float(height)
			if max_width/float(width) < scaling_factor:
				scaling_factor = max_width / float(width)
			# resize image
			img = cv2.resize(img, None, fx=scaling_factor, fy=scaling_factor, interpolation=cv2.INTER_AREA)

		return img
	
	def generate_thumbnail(self) -> Optional[io.BytesIO]:
		if self.vid.isOpened():
			count = 4
			success = True
			while success:
				self.vid.set(cv2.CAP_PROP_POS_MSEC,(count*1000))
				success, image = self.vid.read()
				if success:
					image = self.shrink_image_to_fit(image)
					success, buffer = cv2.imencode(".jpg", image)
				if success:
					io_buf = io.BytesIO(buffer)
					io_buf.seek(0)
					#io_buf.name = "thumbnail.png"
					return io_buf
				count += 1

		return None
