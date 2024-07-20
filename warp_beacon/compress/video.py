import os
import pathlib

import ffmpeg

import logging

class VideoCompress(object):
	video_full_path = ""
	min_audio_bitrate = 32000
	max_audio_bitrate = 256000
	duration = 0.0
	size = 0
	audio_bitrate = 0.0
	video_bitrate = 0.0
	probe = None
	ffmpeg = None

	def __init__(self, file_path: str) -> None:
		self.video_full_path = file_path
		self.ffmpeg = ffmpeg
		self.probe = self.ffmpeg.probe(file_path)
		format_section = self.probe.get("format", {})
		self.duration = float(format_section.get("duration", 0.0))
		self.size = int(format_section.get("size", 0))
		self.audio_bitrate = float(next((s for s in self.probe['streams'] if s['codec_type'] == 'audio'), None).get("bit_rate", 0.0))
		self.video_bitrate = float(next((s for s in self.probe['streams'] if s['codec_type'] == 'video'), None).get("bit_rate", 0.0))

	def __del__(self) -> None:
		pass

	def generate_filepath(self, base_filepath: str) -> str:
		path_info = pathlib.Path(base_filepath)
		ext = path_info.suffix
		old_filename = path_info.stem
		new_filename = "%s_compressed%s" % (old_filename, ext)
		new_filepath = "%s/%s" % (os.path.dirname(base_filepath), new_filename)

		return new_filepath

	def get_size(self) -> int:
		return self.size

	def get_resolution(self) -> tuple:
		video_info = next((s for s in self.probe['streams'] if s['codec_type'] == 'video'), None)
		if video_info:
			return (int(video_info.get("width", 0)), int(video_info.get("height", 0)))

		return (0, 0)

	def get_duration(self) -> float:
		return self.duration

	def compress_to(self, output_file_name: str, target_size: int) -> bool:
		try:
			#if self.size > 50.0:
			#	best_min_size = (32000 + 100000) * (1.073741824 * self.duration) / (8 * 1024)
			#	target_size = best_min_size

			# Target total bitrate, in bps.
			target_total_bitrate = (target_size * 1024 * 8) / (1.073741824 * self.duration)

			audio_bitrate = self.audio_bitrate
			# Target audio bitrate, in bps
			if 10 * audio_bitrate > target_total_bitrate:
				audio_bitrate = target_total_bitrate / 10
				if audio_bitrate < self.min_audio_bitrate < target_total_bitrate:
					audio_bitrate = self.min_audio_bitrate
				elif audio_bitrate > self.max_audio_bitrate:
					audio_bitrate = self.max_audio_bitrate
			# Target video bitrate, in bps.
			video_bitrate = target_total_bitrate - audio_bitrate

			i = ffmpeg.input(self.video_full_path)
			#ffmpeg.output(
			#	i,
			#	os.devnull,
			#	**{'c:v': 'libx264', 'b:v': video_bitrate, 'pass': 1, 'f': 'mp4'}
			#).overwrite_output().run()
			ffmpeg.output(
				i,
				output_file_name,
				**{'preset': 'medium', 'c:v': 'libx264', 'b:v': video_bitrate, 'c:a': 'aac', 'b:a': audio_bitrate}
			).overwrite_output().run()

			return True
		except Exception as e:
			logging.error("Failed to compress video '%s'!", self.video_full_path)
			logging.exception(e)

		return False
