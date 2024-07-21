import io, os

from typing import Union
from PIL import Image
import av

import logging

class VideoInfo(object):
	width = 0
	height = 0
	duration = 0.0
	ffmpeg = None
	filename = ""

	def __init__(self, filename: str) -> None:
		self.filename = filename
		with av.open(file=self.filename, mode='r') as container:
			stream = container.streams.video[0]
			time_base = stream.time_base
			self.duration = float(stream.duration * time_base)
			framerate = stream.average_rate
			frame_container_pts = round((1 / framerate) / time_base)
			container.seek(frame_container_pts, backward=True, stream=stream)
			frame = next(container.decode(video=0))
			self.width = frame.width
			self.height = frame.height
		
	def __del__(self) -> None:
		pass

	def get_demensions(self) -> dict:
		return {"width": self.width, "height": self.height}

	def get_duration(self) -> float:
		return self.duration

	@staticmethod
	def get_filesize(filename: str) -> float:
		return os.stat(filename).st_size / 1024 / 1024
	
	def get_finfo(self, except_info: tuple=()) -> dict:
		res = {}
		res.update(self.get_demensions())
		if "duration" not in except_info:
			res["duration"] = int(self.get_duration())
		if "filesize" not in except_info:
			res["filesize"] = round(VideoInfo.get_filesize(self.filename), 2)
		return res
	
	def shrink_image_to_fit(self, image: Image, size: tuple = (320, 320)) -> Image:
		image.thumbnail(size, Image.Resampling.LANCZOS)
		#image.save(
		#	"/tmp/test.th.jpg",
		#	quality=80,
		#)
		return image
	
	def generate_thumbnail(self) -> Union[io.BytesIO, None]:
		try:
			image = None
			with av.open(file=self.filename, mode='r') as container:
				# Signal that we only want to look at keyframes.
				stream = container.streams.video[0]
				stream.codec_context.skip_frame = "NONKEY"
				frame_num = 10
				time_base = container.streams.video[0].time_base
				framerate = container.streams.video[0].average_rate
				frame_container_pts = round((frame_num / framerate) / time_base)
					
				container.seek(frame_container_pts, backward=True, stream=container.streams.video[0])
				frame = next(container.decode(stream))
				
				image = frame.to_image()
				#image.save(
				#	"/tmp/test.{:04d}.jpg".format(frame.pts),
				#	quality=80,
	 			#)
					#break
			if image:
				image = self.shrink_image_to_fit(image)
				io_buf = io.BytesIO()
				image.save(io_buf, format='JPEG')
				io_buf.seek(0)
				return io_buf
		except Exception as e:
			logging.error("Failed to generate thumbnail!")
			logging.exception(e)

		return None
