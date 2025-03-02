import os
import re
import logging
import requests
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from warp_beacon.jobs import Origin
from warp_beacon.jobs.download_job import DownloadJob

class LinkResolver(object):
	"Resolve short links"
	canonical_link_resolve_re = re.compile(r'<link.*rel="canonical".*href="([^"]+)"\s*/?>')

	@staticmethod
	def extract_youtu_be_link(url: str) -> str:
		try:
			response = requests.get(
					url=url,
					allow_redirects=False,
					timeout=int(os.environ.get("REQUESTS_TIMEOUT", default=60))
				)
			logging.info("Converted URL '%s' to '%s'", url, response.headers["Location"])
			return response.headers["Location"]
		except Exception as e:
			logging.error("Failed to extract YouTube link!")
			logging.exception(e)

		return ''

	@staticmethod
	def extract_youtu_be_link_local(url: str) -> str:
		try:
			parsed = urlparse(url)
			video_id = parsed.path.split('/')[-1] if parsed.path else ''
			query_params = parse_qsl(parsed.query)
			query_params.append(('v', video_id))
			query_params.append(('feature', 'youtu.be'))
			
			new_url = urlunparse((
				parsed.scheme,
				'www.youtube.com',
				'/watch',
				'',  # path parameters
				urlencode(query_params),
				''   # archor
			))
			logging.info("Locally converted URL '%s' to '%s'", url, new_url)
			return new_url
		except Exception as e:
			logging.error("Failed to extract YouTube link!")
			logging.exception(e)

		return ''
	
	@staticmethod
	def resolve_ig_share_link(url: str) -> str:
		'''
		expected url: https://www.instagram.com/share/reel/BAHtk2AamB
		result url: https://www.instagram.com/reel/DAKjQgUNzuH/
		'''
		try:
			content = requests.get(
				url,
				timeout=int(os.environ.get("REQUESTS_TIMEOUT", default=60)
			)).text
			res = re.search(LinkResolver.canonical_link_resolve_re, content)
			new_url = res.group(1).strip()
			logging.info("Converted IG share '%s' link to '%s'", url, new_url)
			return new_url
		except Exception as e:
			logging.error("Failed to convert IG share link!")
			logging.exception(e)

		return url

	@staticmethod
	def resolve_job(job: DownloadJob) -> bool:
		ret = False
		if job.job_origin is Origin.YOUTU_BE:
			job.url = LinkResolver.extract_youtu_be_link(job.url)
			job.job_origin = Origin.YOUTUBE
			ret = True
		if job.job_origin is Origin.INSTAGRAM:
			if "share/" in job.url:
				job.url = LinkResolver.resolve_ig_share_link(job.url)
				ret = True

		return ret