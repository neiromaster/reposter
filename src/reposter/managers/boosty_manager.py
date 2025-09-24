from __future__ import annotations

import asyncio
import json
import os
from asyncio import Event
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

import aiofiles
import httpx
from tqdm import tqdm

from ..config.settings import BoostyConfig, Settings
from ..interfaces.base_manager import BaseManager
from ..models.dto import BoostyAuthData, PreparedVideoAttachment, TelegramPost
from ..utils.log import log
from ..utils.text_utils import extract_tags_from_text


class BoostyManager(BaseManager):
    """Manages Boosty API client and handles posting content to Boosty."""

    BASE_URL = "https://api.boosty.to"

    def __init__(self) -> None:
        """Initialize the manager."""
        super().__init__()
        self._initialized = False
        self._client: httpx.AsyncClient | None = None
        self._blog_name: str = ""
        self._access_token: str | None = None
        self._device_id: str | None = None
        self._auth_path: str = "auth.json"

    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event from the AppManager."""
        super().set_shutdown_event(event)

    async def setup(self, settings: Settings) -> None:
        """Initialize the Boosty manager and the HTTP client."""
        if self._initialized:
            log("🚀 [Boosty] Клиент уже запущен. Перезапуск...", indent=1)
            await self.shutdown()

        log("🚀 [Boosty] Запуск...", indent=1)

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

        self._initialized = True
        log("🚀 [Boosty] Готов к работе.", indent=1)

    async def _authorize(self, blog_name: str) -> None:
        """Authorize using auth.json file for specific blog."""
        log(f"Авторизация в Boosty для блога {blog_name}...", indent=2)

        if not os.path.exists(self._auth_path):
            raise FileNotFoundError(f"Файл авторизации не найден: {self._auth_path}")

        async with aiofiles.open(self._auth_path, encoding="utf-8") as f:
            auth_data_content = await f.read()
            auth_data_dict = json.loads(auth_data_content)
            auth_data = BoostyAuthData.model_validate(auth_data_dict)

        self._access_token = auth_data.access_token
        self._device_id = auth_data.device_id
        self._blog_name = blog_name

        if not self._access_token or not self._device_id:
            raise Exception("access_token и device_id должны быть в файле auth.json")

        if self._client:
            self._client.headers.update(
                {
                    "Authorization": f"Bearer {self._access_token}",
                    "x-from-id": self._device_id,
                    "x-app": "web",
                }
            )
        log("Авторизация успешна!", indent=2)

    async def update_config(self, settings: Settings) -> None:
        """Handles configuration updates."""
        if not self._initialized:
            await self.setup(settings)
            return

        log("🚀 [Boosty] Конфигурация обновлена.", indent=1)

    async def shutdown(self) -> None:
        """Initiates shutdown and closes the client."""
        if not self._initialized:
            return
        log("🚀 [Boosty] Завершение работы...", indent=1)
        # Очищаем сессию
        if self._client:
            await self._client.aclose()
        self._initialized = False
        log("🚀 [Boosty] Остановлен.", indent=1)

    async def __aenter__(self) -> BoostyManager:
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

    async def _sleep_cancelable(self, seconds: int) -> None:
        """Sleep for specified seconds, but can be cancelled by shutdown event."""
        remaining = float(seconds)
        step = 0.25
        while remaining > 0 and (not self._shutdown_event or not self._shutdown_event.is_set()):
            await asyncio.sleep(step)
            remaining -= step

    async def upload_video(self, video_path: str | Path) -> dict[str, Any] | None:
        """Uploads a video to Boosty."""
        if not self._initialized or not self._client:
            raise RuntimeError("Boosty manager not initialized. Call setup() first.")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Видео не найдено: {video_path}")

        self._check_shutdown()

        video_path = str(video_path)
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)

        log(f"📥 [Boosty] Шаг 1/3: Получение URL для загрузки видео: {filename}", indent=2)

        prepare_url = urljoin(self.BASE_URL, "/v1/media_data/video/upload_url")
        params = {"file_name": filename, "container_type": "post_draft"}

        prepare_response = await self._client.get(prepare_url, params=params)

        self._check_shutdown()

        if prepare_response.status_code != 200:
            raise Exception(f"Ошибка подготовки загрузки: {prepare_response.status_code} - {prepare_response.text}")

        upload_data = prepare_response.json()
        upload_url = upload_data["uploadUrl"]
        media_id = upload_data["id"]

        log(f"📥 [Boosty] URL получен. Временный ID: {media_id}", indent=2)
        log("📥 [Boosty] Шаг 2/3: Загрузка видеофайла (последовательно с повторными попытками)...", indent=2)

        async with aiofiles.open(video_path, "rb") as f:
            with tqdm(total=file_size, unit="B", unit_scale=True, desc="Загрузка", mininterval=0.5) as pbar:
                offset = 0
                chunk_size = 1024 * 1024  # 1MB chunks
                while True:
                    self._check_shutdown()

                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break

                    start_byte = offset
                    end_byte = offset + len(chunk) - 1

                    headers = {
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
                        "Content-Type": "application/octet-stream",
                        "Origin": "https://boosty.to",
                        "Referer": f"https://boosty.to/{self._blog_name}/new-post",
                        "X-Uploading-Mode": "parallel",
                    }

                    max_retries = 3
                    retry_delay = 5  # seconds
                    for attempt in range(max_retries):
                        self._check_shutdown()

                        try:
                            response = await self._client.post(
                                upload_url,
                                content=chunk,
                                headers=headers,
                                timeout=30.0,  # 30-секундный таймаут
                            )
                            if response.status_code not in [200, 201]:
                                raise Exception(f"HTTP {response.status_code}")

                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                self._check_shutdown()

                                log(
                                    f"📥 [Boosty] Ошибка загрузки чанка: {e}. "
                                    f"Попытка {attempt + 2}/{max_retries} через {retry_delay} сек...",
                                    indent=3,
                                )
                                await self._sleep_cancelable(retry_delay)
                            else:
                                raise Exception(f"Не удалось загрузить чанк после {max_retries} попыток: {e}") from None

                    offset += len(chunk)
                    pbar.update(len(chunk))

        log("📥 [Boosty] Видеофайл загружен.", indent=2)
        log("📥 [Boosty] Шаг 3/3: Завершение загрузки на сервере Boosty...", indent=2)

        finish_url = urljoin(self.BASE_URL, f"/v1/media_data/video/{media_id}/finish")
        finish_response = await self._client.post(finish_url)

        self._check_shutdown()

        if finish_response.status_code != 200:
            raise Exception(f"Ошибка завершения загрузки: {finish_response.status_code} - {finish_response.text}")

        video_data = finish_response.json()
        log(f"📥 [Boosty] Загрузка завершена. Итоговый ID видео: {video_data.get('id')}", indent=2)

        return video_data

    async def create_post(self, boosty_config: BoostyConfig, post: TelegramPost) -> dict[str, Any] | None:
        """Creates a post on Boosty."""
        if not self._initialized:
            raise RuntimeError("Boosty manager not initialized. Call setup() first.")

        self._check_shutdown()

        await self._authorize(boosty_config.blog_name)

        log(f"📤 [Boosty] Публикация поста в блог {boosty_config.blog_name}", indent=2)

        video_data = None
        for attachment in post.attachments:
            if isinstance(attachment, PreparedVideoAttachment):
                try:
                    video_data = await self.upload_video(attachment.file_path)
                    break
                except Exception as e:
                    log(f"❌ [Boosty] Ошибка загрузки видео: {e}", indent=3)

            self._check_shutdown()

        content_blocks: list[dict[str, Any]] = []
        if video_data:
            content_blocks.append(video_data)
        if post.text:
            content_blocks.append(
                {"type": "text", "modificator": "", "content": json.dumps([post.text, "unstyled", []])}
            )
        if content_blocks:
            content_blocks.append({"content": "", "type": "text", "modificator": "BLOCK_END"})

        teaser_text = (post.text or "Новый пост")[:150]
        teaser_blocks = [
            {"type": "text", "modificator": "", "content": json.dumps([teaser_text, "unstyled", []])},
            {"content": "", "type": "text", "modificator": "BLOCK_END"},
        ]

        tags = extract_tags_from_text(post.text or "")
        form_data = {
            "title": "Новый пост",
            "data": json.dumps(content_blocks),
            "teaser_data": json.dumps(teaser_blocks),
            "tags": json.dumps(tags),
            "deny_comments": "false",
            "wait_video": "false",
            "price": 0,
        }

        publish_url = urljoin(self.BASE_URL, f"/v1/blog/{self._blog_name}/post_draft/publish/")

        log("📤 [Boosty] Публикация поста...", indent=3)

        if not self._client:
            raise RuntimeError("HTTP client not initialized")

        response = await self._client.post(publish_url, data=form_data)

        self._check_shutdown()

        if response.status_code != 200:
            raise Exception(f"Ошибка публикации поста: {response.status_code} — {response.text}")

        result = response.json()
        post_data = result.get("data", {}).get("post", {})
        post_id = post_data.get("id")
        post_url = f"https://boosty.to/{self._blog_name}/posts/{post_id}" if post_id else "Не удалось получить ссылку"

        log(f"📤 [Boosty] Пост успешно опубликован! Ссылка: {post_url}", indent=3)
        return result
