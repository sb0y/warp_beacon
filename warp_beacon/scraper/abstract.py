from abc import ABC, abstractmethod
from typing import Callable, Union

class ScraperAbstract(ABC):
	def __init__(self) -> None:
		pass

	def __del__(self) -> None:
		pass

	@abstractmethod
	def download(self, url: str) -> bool:
		raise NotImplementedError

	@abstractmethod
	def _download_hndlr(self, func: Callable, *args: tuple[str], **kwargs: dict[str]) -> Union[str, dict]:
		raise NotImplementedError

