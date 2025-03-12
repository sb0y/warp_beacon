import numpy as np
import av

from warp_beacon.mediainfo.video import VideoInfo

import logging

class Silencer(VideoInfo):
	def add_silent_audio(self) -> str:
		try:
			new_filepath = self.generate_filepath(self.filename)
			if self.container:
				in_video_stream = next(s for s in self.container.streams if s.type == 'video')
				codec_name = in_video_stream.codec_context.name
				fps = in_video_stream.base_rate
				#time_base = in_video_stream.time_base
				#duration = float(in_video_stream.duration * time_base)
				with av.open(new_filepath, 'w') as out_container:
					out_video_stream = out_container.add_stream(codec_name, rate=fps)
					out_audio_stream = out_container.add_stream('aac')
					out_video_stream.width = in_video_stream.codec_context.width
					out_video_stream.height = in_video_stream.codec_context.height
					out_video_stream.pix_fmt = in_video_stream.codec_context.pix_fmt
					out_video_stream.time_base = in_video_stream.time_base
					for frame in self.container.decode(in_video_stream):
						packet = out_video_stream.encode(frame)
						if packet:
							out_container.mux(packet)
							#
							silent_samples = 64
							silent_data = np.zeros((1, silent_samples), dtype=np.int16)
							#aframe = av.AudioFrame(samples=64, format='s16')
							aframe = av.AudioFrame.from_ndarray(silent_data, layout='mono')
							aframe.pts = frame.pts
							aframe.sample_rate = 44100
							#aframe.rate = 44100

							for packet in out_audio_stream.encode(aframe):
								out_container.mux(packet)

					remain_packets = out_video_stream.encode(None)
					out_container.mux(remain_packets)
				self.filename = new_filepath
				return new_filepath
		except Exception as e:
			logging.error("Error occurred while generating silenced video file!")
			logging.exception(e)

		return ''