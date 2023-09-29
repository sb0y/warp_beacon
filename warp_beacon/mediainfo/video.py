import io
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
			res["width"] = int(self.vid.get(cv2.CV_CAP_PROP_FRAME_WIDTH))
			res["height"] = int(self.vid.get(cv2.CV_CAP_PROP_FRAME_HEIGHT))

		return res

	def get_duration(self) -> int:
		res = None
		if self.vid.isOpened():
			self.vid.set(cv2.CAP_PROP_POS_AVI_RATIO, 1)
			res = int(self.vid.get(cv2.CAP_PROP_POS_MSEC) / 1000)

		return res
	
	def get_finfo(self) -> dict:
		res = {}
		res.update(self.get_demensions())
		res["duration"] = self.get_duration()
		return res
	
	def generate_thumbnail(self) -> io.BytesIO:
		if self.vid.isOpened():
			count = 4
			success = True
			while success:
				self.vid.set(cv2.CAP_PROP_POS_MSEC,(count*1000))
				success, image = self.vid.read()
				if success:
					io_buf = io.BytesIO(image)
					io_buf.seek(0)
					return io_buf
				count += 1

			return None
