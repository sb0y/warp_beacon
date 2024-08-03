from enum import Enum

class JobType(str, Enum):
	UNKNOWN = "unknown",
	VIDEO = "video",
	IMAGE = "image",
	AUDIO = "audio",
	COLLECTION = "collection"
	ANIMATION = "animation"