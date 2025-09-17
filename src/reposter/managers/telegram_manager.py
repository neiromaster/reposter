from __future__ import annotations

import asyncio
from asyncio import Event
from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Any

from pyrogram.client import Client
from pyrogram.errors import ChannelPrivate, FloodWait, PeerIdInvalid, RPCError
from pyrogram.types import (
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from tqdm import tqdm

from ..config.settings import Settings, TelegramConfig
from ..interfaces.base_manager import BaseManager
from ..models.dto import (
    PreparedAttachment,
    PreparedAudioAttachment,
    PreparedDocumentAttachment,
    PreparedPhotoAttachment,
    PreparedVideoAttachment,
    TelegramPost,
)
from ..utils.cleaner import delete_files_async
from ..utils.log import log


class TelegramManager(BaseManager):
    """Manages Kurigram client and handles sending media to Telegram channels."""

    def __init__(self) -> None:
        """Initialize the manager."""
        self._initialized = False
        self._client: Client | None = None
        self._shutdown_event: Event | None = None
        self._pbar: tqdm[Any] | None = None
        self._session_name: str = "user_session"
        self._api_id: int = 0
        self._api_hash: str = ""

    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event from the AppManager."""
        self._shutdown_event = event

    async def setup(self, settings: Settings) -> None:
        """Start the Telegram client session."""
        log("✈️ [Telegram] Инициализация Telegram клиента...")
        self._session_name = settings.app.session_name
        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash

        try:
            self._client = Client(
                self._session_name,
                api_id=self._api_id,
                api_hash=self._api_hash,
            )
            await self._client.start()
            self._initialized = True
            log("✈️ [Telegram] Клиент запущен.")
        except asyncio.CancelledError:
            log("⏹️ Запуск Telegram клиента прерван пользователем.", indent=1)
            self._initialized = False
            raise
        except Exception:
            self._initialized = False
            log("❌ Не удалось запустить Telegram клиент.", indent=1)
            raise

    async def update_config(self, settings: Settings) -> None:
        """Called when the configuration changes."""
        if not self._initialized:
            await self.setup(settings)
            return

        if (
            self._api_id != settings.telegram_api_id
            or self._api_hash != settings.telegram_api_hash
            or self._session_name != settings.app.session_name
        ):
            log("✈️ [Telegram] Конфигурация изменилась, перезапускаю клиент...")
            await self.shutdown()
            await self.setup(settings)

    async def shutdown(self) -> None:
        """Stop the Telegram client session."""
        if self._client and self._client.is_connected:
            await self._client.stop()
            log("✈️ [Telegram] Клиент остановлен.")
        self._initialized = False

    async def __aenter__(self) -> TelegramManager:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and shutdown the client."""
        await self.shutdown()

    async def post_to_channels(self, tg_config: TelegramConfig, posts: list[TelegramPost]) -> None:
        """Sends processed posts to Telegram channels."""
        log(f"✈️ Начало публикации {len(posts)} постов в каналы: {tg_config.channel_ids}", indent=3)

        for post in posts:
            uploaded_items, temp_message_ids = await self._upload_media_to_saved(post.attachments)

            if not uploaded_items:
                if post.text:
                    log("📄 Медиа не найдено, отправляю только текст...", indent=4)
                    for channel_id in tg_config.channel_ids:
                        await self._send_text_to_channel(channel_id, post.text)
                else:
                    log("⚠️ Пост пуст (нет ни медиа, ни текста), пропускаю.", indent=4)
                continue

            caption, text_to_send_separately = self._prepare_caption(post.text)
            self._assign_caption_to_group(uploaded_items, caption)

            for channel_id in tg_config.channel_ids:
                log(f"➡️ Пересылка поста в {channel_id}...", indent=4)
                await self._forward_media_to_channel(channel_id, uploaded_items, text_to_send_separately)

            if temp_message_ids:
                await self._delete_temp_messages(temp_message_ids)

    def _prepare_caption(self, caption: str) -> tuple[str, str | None]:
        """Splits caption if it's too long for a media group."""
        TELEGRAM_CAPTION_LIMIT = 4096
        if len(caption) > TELEGRAM_CAPTION_LIMIT:
            log(
                f"📝 Подпись слишком длинная ({len(caption)} символов). Будет отправлена отдельным сообщением.",
                indent=5,
            )
            return "", caption
        return caption, None

    async def _send_text_to_channel(self, channel_id: int | str, text: str) -> None:
        """Sends a simple text message to a channel."""
        assert self._client is not None
        try:
            await self._client.send_message(chat_id=channel_id, text=text)
        except Exception as e:
            log(f"❌ Ошибка при отправке текста в канал {channel_id}: {e}", indent=5)

    async def _upload_media_to_saved(
        self, attachments: Sequence[PreparedAttachment], max_retries: int = 3
    ) -> tuple[list[InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument], list[int]]:
        """Uploads media to "Saved Messages" and returns media objects and message IDs."""
        assert self._client is not None
        uploaded_items: list[InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument] = []
        temp_message_ids: list[int] = []

        for attachment in attachments:
            attempt = 0
            while attempt < max_retries:
                try:
                    log(f"⬆️ Загрузка {attachment.filename} в Избранное...", indent=5)
                    msg: Message | None = None
                    media_object: InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument | None = None
                    progress_callback = self._create_progress_callback(indent=5)

                    if isinstance(attachment, PreparedVideoAttachment):
                        video_kwargs: dict[str, Any] = {
                            "video": str(attachment.file_path),
                            "file_name": attachment.filename,
                            "width": attachment.width,
                            "height": attachment.height,
                            "progress": progress_callback,
                        }
                        if attachment.thumbnail_path:
                            video_kwargs["thumb"] = str(attachment.thumbnail_path)
                        msg = await self._client.send_video(chat_id="me", **video_kwargs)  # type: ignore[reportUnknownMemberType]
                        if msg and msg.video:
                            media_object = InputMediaVideo(media=msg.video.file_id)

                    elif isinstance(attachment, PreparedAudioAttachment):
                        msg = await self._client.send_audio(  # type: ignore[reportUnknownMemberType]
                            chat_id="me",
                            audio=str(attachment.file_path),
                            file_name=attachment.filename,
                            performer=attachment.artist,
                            title=attachment.title,
                            progress=progress_callback,
                        )
                        if msg and msg.audio:
                            media_object = InputMediaAudio(media=msg.audio.file_id)

                    elif isinstance(attachment, PreparedPhotoAttachment):
                        msg = await self._client.send_photo(  # type: ignore[reportUnknownMemberType]
                            chat_id="me", photo=str(attachment.file_path), progress=progress_callback
                        )
                        if msg and msg.photo:
                            media_object = InputMediaPhoto(media=msg.photo.file_id)

                    elif isinstance(attachment, PreparedDocumentAttachment):
                        msg = await self._client.send_document(  # type: ignore[reportUnknownMemberType]
                            chat_id="me",
                            document=str(attachment.file_path),
                            file_name=attachment.filename,
                            progress=progress_callback,
                        )
                        if msg and msg.document:
                            media_object = InputMediaDocument(media=msg.document.file_id)

                    if msg and msg.id and media_object:
                        temp_message_ids.append(msg.id)
                        uploaded_items.append(media_object)
                    break  # Success

                except FloodWait as e:
                    await self._handle_floodwait(e)
                except RPCError as e:
                    log(f"❌ Ошибка Telegram API при загрузке: {type(e).__name__} — {e}", indent=5)
                    await self._sleep_cancelable(5)
                except Exception as e:
                    log(f"❌ Неизвестная ошибка при загрузке: {e}", indent=5)
                    await self._sleep_cancelable(3)
                attempt += 1

        return uploaded_items, temp_message_ids

    def _assign_caption_to_group(
        self,
        uploaded_items: list[InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument],
        caption: str,
    ) -> None:
        """Assigns caption to the first appropriate media item in a group."""
        if not caption:
            return

        # Priority 1: Photo or Video
        for media in uploaded_items:
            if isinstance(media, (InputMediaPhoto | InputMediaVideo)):
                media.caption = caption
                return
        # Priority 2: Audio
        for media in uploaded_items:
            if isinstance(media, InputMediaAudio):
                media.caption = caption
                return
        # Priority 3: Document
        for media in uploaded_items:
            if isinstance(media, InputMediaDocument):
                media.caption = caption
                return

    async def _forward_media_to_channel(
        self,
        channel_id: int | str,
        uploaded_items: list[InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument],
        separate_text: str | None,
    ) -> None:
        """Forwards uploaded media to a specific channel, respecting group rules."""
        assert self._client is not None
        photo_video_group = [item for item in uploaded_items if isinstance(item, (InputMediaPhoto | InputMediaVideo))]
        audio_group = [item for item in uploaded_items if isinstance(item, InputMediaAudio)]
        doc_group = [item for item in uploaded_items if isinstance(item, InputMediaDocument)]

        try:
            if photo_video_group:
                log(f"📦 Отправка {len(photo_video_group)} фото/видео в канал...", indent=5)
                if len(photo_video_group) > 1:
                    await self._client.send_media_group(chat_id=channel_id, media=photo_video_group)  # type: ignore[reportArgumentType]
                else:
                    item = photo_video_group[0]
                    if isinstance(item, InputMediaPhoto):
                        await self._client.send_photo(chat_id=channel_id, photo=item.media, caption=item.caption)  # type: ignore[reportUnknownMemberType]
                    else:
                        await self._client.send_video(chat_id=channel_id, video=item.media, caption=item.caption)  # type: ignore[reportUnknownMemberType]

            if audio_group:
                log(f"📦 Отправка {len(audio_group)} аудио в канал...", indent=5)
                if len(audio_group) > 1:
                    await self._client.send_media_group(chat_id=channel_id, media=audio_group)  # type: ignore[reportArgumentType]
                else:
                    item = audio_group[0]
                    await self._client.send_audio(chat_id=channel_id, audio=item.media, caption=item.caption)  # type: ignore[reportUnknownMemberType]

            if doc_group:
                log(f"📦 Отправка {len(doc_group)} документов в канал...", indent=5)
                if len(doc_group) > 1:
                    await self._client.send_media_group(chat_id=channel_id, media=doc_group)  # type: ignore[reportArgumentType]
                else:
                    item = doc_group[0]
                    await self._client.send_document(chat_id=channel_id, document=item.media, caption=item.caption)  # type: ignore[reportUnknownMemberType]

            if separate_text:
                await self._send_text_to_channel(channel_id, separate_text)

        except (PeerIdInvalid, ChannelPrivate):
            log(f"⚠️ Канал '{channel_id}' недоступен или приватный. Пропускаю.", indent=5)
        except Exception as e:
            log(f"❌ Ошибка при отправке в канал {channel_id}: {e}", indent=5)

    async def _delete_downloaded_files(self, attachments: Sequence[PreparedAttachment]) -> None:
        """Deletes the locally downloaded files associated with the attachments."""
        await delete_files_async(attachments)

    async def _delete_temp_messages(self, temp_message_ids: list[int]) -> None:
        """Deletes temporary messages from "Saved Messages"."""
        assert self._client is not None
        try:
            await self._client.delete_messages(chat_id="me", message_ids=temp_message_ids)
            log("🧹 Временные сообщения из Избранного удалены.", indent=4)
        except Exception as e:
            log(f"⚠️ Не удалось удалить временные сообщения: {e}", indent=4)

    def _create_progress_callback(self, indent: int) -> Callable[[int, int], None]:
        def _progress_hook(current: int, total: int) -> None:
            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024) if total else 0

            if self._pbar is None:
                self._pbar = tqdm(
                    total=total_mb,
                    unit="MB",
                    unit_scale=False,
                    desc="  " * indent + "🚀 ",
                    ncols=80,
                    bar_format="{desc}{bar}| {n:.0f} / {total:.0f} {unit} | {elapsed} < {remaining} | {rate_fmt}{postfix}",  # noqa: E501
                )

            self._pbar.update(current_mb - self._pbar.n)

            if current >= total:
                self._pbar.close()
                self._pbar = None

        return _progress_hook

    async def _handle_floodwait(self, e: FloodWait) -> None:
        wait_time = e.value if isinstance(e.value, int) else 60
        log(f"⏳ FloodWait: жду {wait_time + 1} секунд...", indent=5)
        await self._sleep_cancelable(wait_time + 1)

    async def _sleep_cancelable(self, seconds: int) -> None:
        remaining = float(seconds)
        step = 0.25
        while remaining > 0:
            if self._shutdown_event and self._shutdown_event.is_set():
                raise asyncio.CancelledError()
            await asyncio.sleep(step)
            remaining -= step
