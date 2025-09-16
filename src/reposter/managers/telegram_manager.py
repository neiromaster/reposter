from __future__ import annotations

import asyncio
from asyncio import Event
from collections.abc import Callable
from pathlib import Path
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
from ..models.dto import Post
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

    async def post_to_channels(self, tg_config: TelegramConfig, posts: list[Post]) -> None:
        """Placeholder for posting to channels."""
        log(f"✈️ Начало публикации в каналы: {tg_config.channel_ids}")
        # This is a placeholder. The actual implementation will go here.
        # It will involve iterating through posts, getting downloaded
        # media paths from another manager, and calling self.send_media.
        await asyncio.sleep(0)  # Simulate async work

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

    async def send_media(self, channel: int | str, files: list[Path], caption: str = "", max_retries: int = 3) -> None:
        """
        Sends media (single or album) to a Telegram channel by first uploading to "Saved Messages".
        """
        assert self._client is not None, "TelegramManager is not started"

        await self._send_via_saved(channel, files, caption, max_retries)

    async def _send_via_saved(
        self,
        channel: int | str,
        files: list[Path],
        caption: str,
        max_retries: int,
    ) -> None:
        """
        Uploads media to "Saved Messages", then sends it to the target channel.
        Correctly groups media based on Telegram's rules and preserves order.
        """
        assert self._client is not None

        TELEGRAM_CAPTION_LIMIT = 4096
        caption_to_send = caption
        text_to_send_separately = None

        if len(caption) > TELEGRAM_CAPTION_LIMIT:
            log(
                f"📝 Подпись слишком длинная ({len(caption)} символов). Она будет отправлена отдельным сообщением.",
                indent=3,
            )
            caption_to_send = ""  # Caption will be handled later
            text_to_send_separately = caption

        # Step 1: Upload all media and store them, preserving order
        uploaded_items: list[InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument] = []
        temp_message_ids: list[int] = []

        for file_path in files:
            suffix = file_path.suffix.lower()
            attempt = 0
            while attempt < max_retries:
                try:
                    log(f"⬆️ Загрузка {file_path.name} в Избранное...", indent=4)
                    msg: Message | None = None
                    media_object: InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument | None = None

                    if suffix in [".jpg", ".jpeg", ".png", ".webp"]:
                        msg = await self._client.send_photo(  # type: ignore[reportUnknownMemberType]
                            chat_id="me", photo=str(file_path), progress=self._create_progress_callback(indent=4)
                        )
                        if msg and msg.photo:
                            media_object = InputMediaPhoto(media=msg.photo.file_id)

                    elif suffix in [".mp4", ".mov", ".mkv"]:
                        msg = await self._client.send_video(  # type: ignore[reportUnknownMemberType]
                            chat_id="me", video=str(file_path), progress=self._create_progress_callback(indent=4)
                        )
                        if msg and msg.video:
                            media_object = InputMediaVideo(media=msg.video.file_id)

                    elif suffix in [".mp3", ".ogg", ".wav", ".flac", ".m4a"]:
                        msg = await self._client.send_audio(  # type: ignore[reportUnknownMemberType]
                            chat_id="me", audio=str(file_path), progress=self._create_progress_callback(indent=4)
                        )
                        if msg and msg.audio:
                            media_object = InputMediaAudio(media=msg.audio.file_id)

                    else:  # Treat as a document
                        msg = await self._client.send_document(  # type: ignore[reportUnknownMemberType]
                            chat_id="me", document=str(file_path), progress=self._create_progress_callback(indent=4)
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
                    log(f"❌ Ошибка Telegram API: {type(e).__name__} — {e}", indent=4)
                    await self._sleep_cancelable(5)
                except Exception as e:
                    log(f"❌ Неизвестная ошибка отправки: {e}", indent=4)
                    await self._sleep_cancelable(3)
                attempt += 1

        if not uploaded_items:
            log("⚠️ Не удалось загрузить ни одного медиафайла для отправки.", indent=4)
            return

        # Step 2: Assign caption according to priority
        caption_assigned = False
        # Priority 1: Photo or Video
        for media in uploaded_items:
            if isinstance(media, (InputMediaPhoto | InputMediaVideo)):
                media.caption = caption_to_send
                caption_assigned = True
                break
        # Priority 2: Audio
        if not caption_assigned:
            for media in uploaded_items:
                if isinstance(media, InputMediaAudio):
                    media.caption = caption_to_send
                    caption_assigned = True
                    break
        # Priority 3: Document
        if not caption_assigned:
            for media in uploaded_items:
                if isinstance(media, InputMediaDocument):
                    media.caption = caption_to_send
                    break

        # Step 3: Group and send
        photo_video_group = [
            media for media in uploaded_items if isinstance(media, (InputMediaPhoto | InputMediaVideo))
        ]
        audio_group = [media for media in uploaded_items if isinstance(media, InputMediaAudio)]
        doc_group = [media for media in uploaded_items if isinstance(media, InputMediaDocument)]

        try:
            if photo_video_group:
                log(f"📦 Отправка {len(photo_video_group)} фото/видео в канал...", indent=4)
                if len(photo_video_group) > 1:
                    await self._client.send_media_group(chat_id=channel, media=photo_video_group)  # type: ignore[reportArgumentType]
                else:
                    item = photo_video_group[0]
                    if isinstance(item, InputMediaPhoto):
                        await self._client.send_photo(chat_id=channel, photo=item.media, caption=item.caption)  # type: ignore[reportUnknownMemberType]
                    else:
                        await self._client.send_video(chat_id=channel, video=item.media, caption=item.caption)  # type: ignore[reportUnknownMemberType]

            if audio_group:
                log(f"📦 Отправка {len(audio_group)} аудио в канал...", indent=4)
                if len(audio_group) > 1:
                    await self._client.send_media_group(chat_id=channel, media=audio_group)  # type: ignore[reportArgumentType]
                else:
                    item = audio_group[0]
                    await self._client.send_audio(  # type: ignore[reportUnknownMemberType]
                        chat_id=channel, audio=item.media, caption=item.caption
                    )

            if doc_group:
                log(f"📦 Отправка {len(doc_group)} документов в канал...", indent=4)
                if len(doc_group) > 1:
                    await self._client.send_media_group(chat_id=channel, media=doc_group)  # type: ignore[reportArgumentType]
                else:
                    item = doc_group[0]
                    await self._client.send_document(  # type: ignore[reportUnknownMemberType]
                        chat_id=channel, document=item.media, caption=item.caption
                    )

            if text_to_send_separately:
                log("✍️ Отправка длинного текста отдельным сообщением...", indent=4)
                await self._client.send_message(chat_id=channel, text=text_to_send_separately)

        except (PeerIdInvalid, ChannelPrivate):
            log(f"⚠️ Канал '{channel}' недоступен или приватный. Пропускаю.", indent=4)
        except Exception as e:
            log(f"❌ Ошибка при отправке в канал: {e}", indent=4)

        if temp_message_ids:
            try:
                await self._client.delete_messages(chat_id="me", message_ids=temp_message_ids)
                log("🧹 Временные сообщения из Избранного удалены.", indent=4)
            except Exception as e:
                log(f"⚠️ Не удалось удалить временные сообщения: {e}", indent=4)

    async def _handle_floodwait(self, e: FloodWait) -> None:
        wait_time = e.value if isinstance(e.value, int) else 60
        log(f"⏳ FloodWait: жду {wait_time + 1} секунд...", indent=4)
        await self._sleep_cancelable(wait_time + 1)

    async def _sleep_cancelable(self, seconds: int) -> None:
        remaining = float(seconds)
        step = 0.25
        while remaining > 0:
            if self._shutdown_event and self._shutdown_event.is_set():
                raise asyncio.CancelledError()
            await asyncio.sleep(step)
            remaining -= step
