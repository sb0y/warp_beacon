from enum import Flag, auto

class XMediaType(Flag):
	UNKNOWN = 0
	VIDEO = auto()
	IMAGE = auto()
	MIXED = auto()
	PLAYLIST = auto()