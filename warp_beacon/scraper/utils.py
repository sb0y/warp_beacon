import logging

from fake_useragent import UserAgent

class ScraperUtils(object):
	@staticmethod
	def get_ua_dict(browsers: list=['Facebook', 'Android'], platforms: list=['mobile', 'tablet'], os: list=['Android', 'iOS']) -> dict:
		random_client = None
		try:
			ua = UserAgent(browsers=browsers, platforms=platforms, os=os)
			random_client = ua.getRandom
			logging.info("Select random UA: %s", random_client)
		except Exception as e:
			logging.warning("Exception occurrd while generating random client UA!", exc_info=e)
			random_client = {'useragent': 'Mozilla/5.0 (Linux; Android 14; SM-S911B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/133.0.6943.117 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/502.0.0.66.79;IABMV/1;]', 'percent': 0.017937771404345798, 'type': 'mobile', 'device_brand': 'Samsung', 'browser': 'Facebook', 'browser_version': '502.0.0', 'browser_version_major_minor': 502.0, 'os': 'Android', 'os_version': '14', 'platform': 'Linux aarch64'}
		return random_client

	@staticmethod
	def get_ua(browsers: list=['Facebook', 'Android'], platforms: list=['mobile', 'tablet'], os: list=['Android', 'iOS']) -> str:
		return ScraperUtils.get_ua_dict(browsers=browsers, platforms=platforms, os=os)["useragent"]