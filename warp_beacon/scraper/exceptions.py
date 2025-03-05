class ScraperError(Exception):
	def __init__(self, *args, **kwargs):
		args = list(args)
		if len(args) > 0:
			self.message = str(args.pop(0))
		for key in list(kwargs.keys()):
			setattr(self, key, kwargs.pop(key))
		if not self.message:
			self.message = "{title} ({body})".format(
				title=getattr(self, "reason", "Unknown"),
				body=getattr(self, "error_type", vars(self)),
			)
		super().__init__(self.message, *args, **kwargs)
		if hasattr(self, "response") and self.response:
			self.code = self.response.status_code

class TimeOut(ScraperError):
	pass

class FileTooBig(ScraperError):
	pass

class NotFound(ScraperError):
	pass

class Unavailable(ScraperError):
	pass

class YoutubeLiveError(ScraperError):
	pass

class YotubeAgeRestrictedError(ScraperError):
	pass

class IGRateLimitOccurred(ScraperError):
	pass

class CaptchaIssue(ScraperError):
	pass

class AllAccountsFailed(ScraperError):
	pass

class UnknownError(ScraperError):
	pass

def extract_exception_message(e: Exception) -> str:
	msg = ""
	if hasattr(e, "expected"):
		msg = "Expected bytes: %d" % int(e.expected)
	elif hasattr(e, "error_string"):
		msg = e.error_string
	elif hasattr(e, "message"):
		msg = e.message
	elif hasattr(e, "reason"):
		msg = e.reason
	elif hasattr(e, "args"):
		msg = str(e.args)
		
	return msg