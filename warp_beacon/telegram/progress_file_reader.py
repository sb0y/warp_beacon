import io
import os
from types import TracebackType
from typing import Optional, Callable, Type

class ProgressFileReader(io.BufferedReader):
	def __init__(self, file_path: str, callback: Optional[Callable[[str, int, int], None]]) -> None:
		raw = open(file_path, "rb")
		super().__init__(raw)
		self._raw = raw
		self.callback = callback
		self.total = os.path.getsize(file_path)
		self.read_bytes = 0
		self.name = os.path.basename(file_path)

	def read(self, size: int = -1) -> bytes:
		chunk = super().read(size)
		self.read_bytes += len(chunk)
		if self.callback:
			self.callback(self.name, self.read_bytes, self.total)
		return chunk

	def close(self) -> None:
		if not self.closed:
			super().close()
			self._raw.close()

	def __enter__(self) -> "ProgressFileReader":
		return self

	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_val: Optional[BaseException],
		exc_tb: Optional[TracebackType]
	) -> None:
		self.close()