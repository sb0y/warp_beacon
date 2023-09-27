from abc import ABC, abstractmethod

class ScraplerAbstract(ABC):
	def __init__(self) -> None:
		pass

	def __del__(self) -> None:
		pass

	@abstractmethod
	def scrap(self, url: str) -> str:
		raise NotImplementedError

	@abstractmethod
	def download(self, url: str) -> bool:
		raise NotImplementedError
