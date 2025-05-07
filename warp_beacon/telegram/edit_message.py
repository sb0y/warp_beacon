from pyrogram.client import Client
from pyrogram.types import InputMedia, InputMediaAudio, InputMediaPhoto, InputMediaVideo, InputMediaAnimation, InlineKeyboardMarkup
from pyrogram import raw
from pyrogram import types

from warp_beacon.telegram.progress_bar import ProgressBar
from warp_beacon.telegram.types import ReportType

class EditMessage(object):
	def __init__(self, client: Client) -> None:
		self.client = client

	def get_wrapped_video(self, raw_file: raw.base.InputFile, raw_thumb: raw.base.InputFile, media: InputMediaVideo, file_name: str = None) -> raw.types.InputMediaUploadedDocument:
		return raw.types.InputMediaUploadedDocument(
				file=raw_file,
				mime_type=self.client.guess_mime_type(media.media) or "video/mp4",
				thumb=raw_thumb,
				spoiler=media.has_spoiler,
				attributes=[
					raw.types.DocumentAttributeVideo(
						duration=media.duration,
						w=media.width,
						h=media.height,
						supports_streaming=media.supports_streaming
					),
					raw.types.DocumentAttributeFilename(
						file_name=file_name
					)
				]
			)
	
	def get_wrapped_photo(self, raw_file: raw.base.InputFile, media: InputMediaPhoto) -> raw.types.InputMediaUploadedPhoto:
		return raw.types.InputMediaUploadedPhoto(
			file=raw_file,
			spoiler=media.has_spoiler
		)
	
	def get_wrapped_audio(self, raw_file: raw.base.InputFile, raw_thumb: raw.base.InputFile, media: InputMediaAudio, file_name: str = None) -> raw.types.InputMediaUploadedDocument:
		return raw.types.InputMediaUploadedDocument(
			mime_type=self.client.guess_mime_type(media.media) or "audio/mpeg",
			thumb=raw_thumb,
			file=raw_file,
			attributes=[
				raw.types.DocumentAttributeAudio(
					duration=media.duration,
					performer=media.performer,
					title=media.title
				),
				raw.types.DocumentAttributeFilename(
					file_name=file_name
				)
			]
		)
	
	def get_wrapped_animation(self, raw_file: raw.base.InputFile, raw_thumb: raw.base.InputFile, media: InputMediaVideo, file_name: str = None) -> raw.types.InputMediaUploadedDocument:
		return raw.types.InputMediaUploadedDocument(
			mime_type=self.client.guess_mime_type(media.media) or "video/mp4",
			thumb=raw_thumb,
			spoiler=media.has_spoiler,
			file=raw_file,
			attributes=[
				raw.types.DocumentAttributeVideo(
					supports_streaming=True,
					duration=media.duration,
					w=media.width,
					h=media.height
				),
				raw.types.DocumentAttributeFilename(
					file_name=file_name
				),
				raw.types.DocumentAttributeAnimated()
			]
		)

	#async def upload_with_progress(self,
	#	media: InputMedia | InputMediaAudio | InputMediaPhoto | InputMediaVideo | InputMediaAnimation,
	#	chat_id: int | str,
	#	message_id: int,
	#	file_name: str
	#) -> raw.base.InputFile:
	#	progress_bar = ProgressBar(self.client)
	#	progress_id = f"{chat_id}:{message_id}:{file_name}"
	#	self.progress_bars[progress_id] = progress_bar
	#	raw_file = await self.client.save_file(path=media.media, progress=progress_bar.progress_callback, progress_args=(chat_id, message_id, file_name,))
	#	del self.progress_bars[progress_id]
	#	return raw_file

	async def edit(self,
		chat_id: int | str,
		message_id: int,
		media: InputMedia | InputMediaAudio | InputMediaPhoto | InputMediaVideo | InputMediaAnimation,
		reply_markup: InlineKeyboardMarkup = None,
		file_name: str = None
	) -> None:
		progress_bar = ProgressBar(self.client)
		await progress_bar.progress_callback(current=0, total=0, chat_id=chat_id, message_id=message_id, operation="Uploading", label=file_name, report_type=ReportType.PROGRESS)
		raw_file = await self.client.save_file(path=media.media, progress=progress_bar.progress_callback, progress_args=(chat_id, message_id, "Uploading", ReportType.PROGRESS, file_name))

		caption = media.caption
		parse_mode = media.parse_mode

		message, entities = None, None

		if caption is not None:
			message, entities = (await self.client.parser.parse(caption, parse_mode)).values()

		raw_media = None
		if isinstance(media, types.InputMediaVideo):
			#progress_bar_thumb = ProgressBar(self.client)
			raw_file_thumb = await self.client.save_file(path=media.thumb)
			raw_media = self.get_wrapped_video(raw_file=raw_file, raw_thumb=raw_file_thumb, media=media, file_name=file_name)
		elif isinstance(media, types.InputMediaPhoto):
			raw_media = self.get_wrapped_photo(raw_file=raw_file, media=media)
		elif isinstance(media, types.InputMediaAudio):
			#progress_bar_thumb = ProgressBar(self.client)
			raw_file_thumb = await self.client.save_file(path=media.thumb)
			raw_media = self.get_wrapped_audio(raw_file=raw_file, raw_thumb=raw_file_thumb, media=media, file_name=file_name)
		elif isinstance(media, types.InputMediaAnimation):
			#progress_bar_thumb = ProgressBar(self.client)
			raw_file_thumb = await self.client.save_file(path=media.thumb)
			raw_media = self.get_wrapped_animation(raw_file=raw_file, raw_thumb=raw_file_thumb, media=media, file_name=file_name)

		peer = await self.client.resolve_peer(chat_id)

		r = await self.client.invoke(
			raw.functions.messages.EditMessage(
				peer=peer,
				id=message_id,
				media=raw_media,
				reply_markup=await reply_markup.write(self.client) if reply_markup else None,
				message=message,
				entities=entities
			)
		)

		for i in r.updates:
			if isinstance(i, (raw.types.UpdateEditMessage, raw.types.UpdateEditChannelMessage)):
				return await types.Message._parse(
					self.client, i.message,
					{i.id: i for i in r.users},
					{i.id: i for i in r.chats}
				)