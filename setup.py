import codecs
import os.path

from setuptools import setup

def read(rel_path: str) -> str:
	here = os.path.abspath(os.path.dirname(__file__))
	with codecs.open(os.path.join(here, rel_path), 'r') as fp:
		return fp.read()

def get_version(rel_path: str) -> str:
	for line in read(rel_path).splitlines():
		if line.startswith('__version__'):
			delim = '"' if '"' in line else "'"
			return line.split(delim)[1]
	else:
		raise RuntimeError("Unable to find version string.")

setup(
	name="warp_beacon",
	version=get_version("warp_beacon/__version__.py"),
	author="Andrey Bagrintsev",
	author_email="andrey@bagrintsev.me",
	description="Telegram bot for expanding external media links",  # noqa: W605
	include_package_data=True,
	classifiers=[
		'Development Status :: 5 - Production/Stable',

		'Topic :: Sociology',
		'Topic :: Communications :: File Sharing',
		'Topic :: Internet :: WWW/HTTP',
		'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
		'Topic :: Scientific/Engineering :: Image Processing',
		'Topic :: Multimedia :: Video',
		'Topic :: Multimedia',

		'License :: OSI Approved :: Apache Software License',

		# Specify operating system
		'Operating System :: POSIX :: Linux',

		# Specify the Python versions you support here. In particular, ensure
		'Programming Language :: Python :: 3.10'
	],
	license="Apache License",
	url="https://github.com/sb0y/warp_beacon",
	packages=[
		'warp_beacon',
		'warp_beacon/telegram',
		'warp_beacon/uploader',
		'warp_beacon/storage',
		'warp_beacon/scraper',
		'warp_beacon/scraper/instagram',
		'warp_beacon/scraper/youtube',
		'warp_beacon/scraper/X',
		'warp_beacon/mediainfo',
		'warp_beacon/jobs',
		'warp_beacon/compress',
		'warp_beacon/scheduler'
	],
	py_modules=[
		"warp_beacon/__version__",
		"warp_beacon/warp_beacon",
		"warp_beacon/yt_auth",
		"warp_beacon/telegram/bot",
		"warp_beacon/telegram/placeholder_message",
		"warp_beacon/telegram/handlers",
		"warp_beacon/telegram/utils",
		"warp_beacon/telegram/caption_shortener",
		"warp_beacon/telegram/progress_bar",
		"warp_beacon/telegram/progress_file_reader",
		"warp_beacon/telegram/edit_message",
		"warp_beacon/telegram/download_status",
		"warp_beacon/telegram/types",
		"warp_beacon/jobs/abstract",
		"warp_beacon/jobs/download_job",
		"warp_beacon/jobs/upload_job",
		"warp_beacon/mediainfo/abstract",
		"warp_beacon/mediainfo/video",
		"warp_beacon/mediainfo/audio",
		"warp_beacon/mediainfo/silencer",
		"warp_beacon/compress/video",
		"warp_beacon/scheduler/scheduler",
		"warp_beacon/scheduler/instagram_human",
		"warp_beacon/scraper/abstract",
		"warp_beacon/scraper/exceptions",
		"warp_beacon/scraper/types",
		"warp_beacon/scraper/instagram/instagram",
		"warp_beacon/scraper/instagram/wb_instagrapi",
		"warp_beacon/scraper/account_selector",
		"warp_beacon/scraper/youtube/abstract",
		"warp_beacon/scraper/youtube/youtube",
		"warp_beacon/scraper/youtube/shorts",
		"warp_beacon/scraper/youtube/music",
		"warp_beacon/scraper/X/abstract",
		"warp_beacon/scraper/X/X",
		"warp_beacon/scraper/X/types",
		"warp_beacon/scraper/fail_handler",
		"warp_beacon/scraper/link_resolver",
		"warp_beacon/scraper/utils",
		"warp_beacon/storage/mongo"
	],
	#scripts=['scripts/wait_dc_update.py'],
	data_files=[
		("/lib/systemd/system/",
			["etc/warp_beacon.service"]
		),
		("/etc/warp_beacon/",
			["etc/warp_beacon.conf"]
		),
		("/var/warp_beacon/",
			["assets/placeholder.gif"]
		),
		("/var/warp_beacon/",
			["etc/accounts.json"]
		),
		("/var/warp_beacon/",
			["etc/proxies.json"]
		)
	],

	#entry_points={
	#	'console_scripts': [
	#		'warp_beacon = warp_beacon.warp_beacon:main'
	#	]
	#}
)
