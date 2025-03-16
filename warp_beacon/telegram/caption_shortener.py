import logging
from typing import Union
from bs4 import NavigableString, Tag, Comment
from bs4 import BeautifulSoup

CAPTION_LENGTH_LIMIT = 130

class CaptionShortner(object):
	@staticmethod
	def strip_html(text: str) -> str:
		try:
			soup = BeautifulSoup(text, "html.parser")
			return soup.get_text()
		except Exception as e:
			logging.warning("Failed to stript HTML tags!")
			logging.exception(e)

		return text

	@staticmethod
	def need_short(text: str) -> bool:
		wo_html = CaptionShortner.strip_html(text)
		if len(wo_html) > CAPTION_LENGTH_LIMIT:
			return True
		return False

	@staticmethod
	def smart_truncate_html(html: str, limit: int = CAPTION_LENGTH_LIMIT) -> str:
		result = ""
		try:
			soup = BeautifulSoup(html, "html.parser")
			length = 0

			def walk(node: Union[NavigableString, Tag, Comment]) -> None:
				nonlocal result, length
				if length >= limit:
					return

				if isinstance(node, str):
					words = node.split()
					for word in words:
						if length + len(word) + 1 > limit:
							return
						if result and not result.endswith(" "):
							result += " "
							length += 1
						result += word
						length += len(word)
				elif isinstance(node, Tag):
					if node.name == '[document]':
						for child in node.children:
							walk(child)
						return

					for child in node.children:
						walk(child)
						if length >= limit:
							break

					result += f"</{node.name}>"

			walk(soup)
		except Exception as e:
			logging.warning("Fail in smart_truncate_html!")
			logging.exception(e)
		return result