import io
import os
from types import TracebackType
from typing import Optional, Callable, Type

class ProgressFileReader(io.FileIO):
	def __init__(self, file_path: str, callback: Optional[Callable[[str, int, int], None]]) -> None:
		super().__init__(file_path, "rb")
		self.callback = callback
		self._total = os.path.getsize(file_path)
		self._read_bytes = 0
		self._display_name = os.path.basename(file_path)

	def __fspath__(self) -> str:
		return self._display_name 

	def read(self, size: int = -1) -> bytes:
		chunk = super().read(size)
		self._read_bytes += len(chunk)
		if self.callback:
			self.callback(self._display_name, self._read_bytes, self._total)
		return chunk

	def close(self) -> None:
		if not self.closed:
			super().close()

	def __enter__(self) -> "ProgressFileReader":
		return self

	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_val: Optional[BaseException],
		exc_tb: Optional[TracebackType]
	) -> None:
		self.close()