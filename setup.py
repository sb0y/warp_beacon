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
		'warp_beacon/uploader',
		'warp_beacon/storage',
		'warp_beacon/scrapler',
		'warp_beacon/mediainfo',
		'warp_beacon/jobs'
	],
	py_modules=[
		"warp_beacon/__version__",
		"warp_beacon/warp_beacon",
		"warp_beacon/jobs/abstract",
		"warp_beacon/jobs/download_job",
		"warp_beacon/jobs/upload_job",
		"warp_beacon/mediainfo/video",
		"warp_beacon/scrapler/abstract",
		"warp_beacon/scrapler/instagram"
	],
	#scripts=['scripts/wait_dc_update.py'],
	data_files=[
		("/lib/systemd/system/",
			["etc/warp_beacon.service"]
		),
		("/etc/warp_beacon/",
			["etc/warp_beacon.conf"]
		)
	],

	#entry_points={
	#	'console_scripts': [
	#		'warp_beacon = warp_beacon.warp_beacon:main'
	#	]
	#}
)
