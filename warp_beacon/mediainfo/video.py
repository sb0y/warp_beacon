import io

from typing import Union

from warp_beacon.mediainfo.abstract import MediaInfoAbstract

import logging

class VideoInfo(MediaInfoAbstract):
	width = 0
	height = 0

	def __init__(self, filename: str) -> None:
		super(VideoInfo, self).__init__(filename)
		
		if self.container:
			stream = next(s for s in self.container.streams if s.type == 'video')
			time_base = stream.time_base
			self.duration = float(stream.duration * time_base)
			framerate = stream.average_rate
			frame_container_pts = round((1 / framerate) / time_base)
			# !
			self.container.seek(frame_container_pts, backward=True, stream=stream)
			#
			frame = next(self.container.decode(stream))
			self.width = frame.width
			self.height = frame.height
			# restore original position after previous frame search
			self.container.seek(0, backward=False, stream=stream)

	def get_demensions(self) -> dict:
		return {"width": self.width, "height": self.height}

	def get_finfo(self, except_info: tuple=()) -> dict:
		res = {}
		res.update(self.get_demensions())
		if "duration" not in except_info:
			res["duration"] = round(self.get_duration())
		if "filesize" not in except_info:
			res["filesize"] = VideoInfo.get_filesize(self.filename)
		return res
	
	def generate_thumbnail(self) -> Union[io.BytesIO, None]:
		try:
			image = None
			if self.container:
				# Signal that we only want to look at keyframes.
				stream = self.container.streams.video[0]
				stream.codec_context.skip_frame = "NONKEY"
				frame_num = 120
				time_base = stream.time_base
				framerate = stream.average_rate
				frame_container_pts = round((frame_num / framerate) / time_base)
					
				self.container.seek(frame_container_pts, backward=True, stream=stream)
				frame = next(self.container.decode(stream))
				
				image = frame.to_image()
				#image.save(
				#	"/tmp/test.{:04d}.jpg".format(frame.pts),
				#	quality=80,
	 			#)
					#break
			if image:
				image = VideoInfo.shrink_image_to_fit(image)
				io_buf = io.BytesIO()
				image.save(io_buf, format='JPEG')
				io_buf.seek(0)
				return io_buf
		except Exception as e:
			logging.error("Failed to generate thumbnail!")
			logging.exception(e)

		return None

	def has_sound(self) -> bool:
		try:
			if self.container:
				stream_list = self.container.streams.get(audio=0)
				if len(stream_list) > 0:
					return True
		except Exception as e:
			logging.warning("An exception occurred while detection audio track!")
			#logging.exception(e)

		return False