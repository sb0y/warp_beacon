from warp_beacon.mediainfo.abstract import MediaInfoAbstract

class AudioInfo(MediaInfoAbstract):
	def __init__(self, filename: str) -> None:
		super(AudioInfo, self).__init__(filename)
		if self.container:
			stream_list = self.container.streams.get(audio=0)
			if stream_list:
				stream = stream_list[0]
				time_base = stream.time_base
				self.duration = float(stream.duration * time_base)

	def get_finfo(self, except_info: tuple=()) -> dict:
		res = {}
		if "duration" not in except_info:
			res["duration"] = round(self.get_duration())
		if "filesize" not in except_info:
			res["filesize"] = AudioInfo.get_filesize(self.filename)
		return res