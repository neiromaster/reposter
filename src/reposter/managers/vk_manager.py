from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import anyio
import httpx
from pydantic import HttpUrl
from tenacity import (
    RetryCallState,
    RetryError,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from ..config.settings import Settings
from ..interfaces.base_manager import BaseManager
from ..models.dto import Post, WallGetResponse
from ..utils.cleaner import normalize_links


class VKManager(BaseManager):
    def __init__(self) -> None:
        self._initialized: bool = False
        self._token: str = ""
        self._client: httpx.AsyncClient | None = None
        self._shutdown_event = asyncio.Event()

    async def setup(self, settings: Settings) -> None:
        """Initializes the VK manager and the HTTP client."""
        print("🌐 [VK] Инициализация VK API...")
        self._token = settings.vk_service_token
        self._shutdown_event.clear()

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            http2=True,
            headers={"User-Agent": "Reposter/1.0"},
            follow_redirects=True,
        )
        self._initialized = True
        print("🌐 [VK] Клиент запущен и готов к работе.")

    async def update_config(self, settings: Settings) -> None:
        """Handles configuration updates."""
        if not self._initialized:
            await self.setup(settings)
            return

        if self._token != settings.vk_service_token:
            print("🌐 [VK] Токен изменился, перезапускаю клиент...")
            await self.shutdown()
            await self.setup(settings)
        else:
            print("🌐 [VK] Конфиг обновлён, токен не изменился.")

    async def shutdown(self) -> None:
        """Initiates shutdown and closes the client."""
        if not self._initialized:
            return
        print("🌐 [VK] Инициирую остановку клиента...")
        self._shutdown_event.set()
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._initialized = False
        print("🌐 [VK] Клиент остановлен.")

    async def _should_retry(self, retry_state: RetryCallState) -> bool:
        """Return True if the exception is retryable and shutdown is not requested."""
        if self._shutdown_event.is_set():
            return False
        if not retry_state.outcome:
            return False
        exc = retry_state.outcome.exception()
        if isinstance(exc, asyncio.CancelledError):
            return False
        return isinstance(exc, (httpx.RequestError | httpx.HTTPStatusError | RuntimeError))

    async def _before_sleep(self, retry_state: RetryCallState) -> None:
        """Log before sleeping."""
        if retry_state.outcome and retry_state.next_action:
            print(
                f"  ❌ [VK] Ошибка: {retry_state.outcome.exception()}. "
                f"Повтор через {retry_state.next_action.sleep:.2f} c..."
            )

    async def download_file(self, url: HttpUrl, download_path: Path) -> Path | None:
        """Downloads a file from a given URL with retries and saves it."""

        @retry(
            wait=wait_exponential(multiplier=2, min=2, max=10),
            stop=stop_after_attempt(3),
            retry=self._should_retry,
            before_sleep=self._before_sleep,
            retry_error_cls=RetryError,
        )
        async def _download() -> Path | None:
            if self._shutdown_event.is_set():
                raise asyncio.CancelledError("Shutdown requested")
            assert self._client is not None
            if not url.path:
                return None
            save_path = download_path / Path(url.path).name
            save_path.parent.mkdir(exist_ok=True, parents=True)
            try:
                async with self._client.stream("GET", str(url)) as resp:
                    resp.raise_for_status()
                    async with await anyio.open_file(save_path, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if self._shutdown_event.is_set():
                                raise asyncio.CancelledError("Shutdown requested")
                            await f.write(chunk)
                print(f"  ✅ [VK] Файл сохранен: {save_path.name}")
                return save_path
            except (Exception, asyncio.CancelledError) as e:
                if save_path.exists():
                    save_path.unlink()
                if isinstance(e, asyncio.CancelledError):
                    print("  ⏹️ [VK] Загрузка файла прервана.")
                raise

        return await _download()

    async def get_vk_wall(self, domain: str, post_count: int, post_source: str) -> list[Post]:
        """Requests posts from a VK wall (or Donut) with retry and cancellation."""

        @retry(
            wait=wait_exponential(multiplier=2, min=2, max=10),
            stop=stop_after_attempt(3),
            retry=self._should_retry,
            before_sleep=self._before_sleep,
            retry_error_cls=RetryError,
        )
        async def _get_wall(params: dict[str, Any]) -> list[Post]:
            if self._shutdown_event.is_set():
                raise asyncio.CancelledError("Shutdown requested")
            assert self._client is not None

            resp = await self._client.get("https://api.vk.com/method/wall.get", params=params)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"VK API Error: {data['error']['error_msg']}")
            posts = WallGetResponse.model_validate(data["response"]).items
            for post in posts:
                if post.text:
                    post.text = normalize_links(post.text)
            return posts

        if self._shutdown_event.is_set():
            raise asyncio.CancelledError("Shutdown requested")

        params: dict[str, Any] = {
            "domain": domain,
            "count": post_count,
            "access_token": self._token,
            "v": "5.199",
        }
        if post_source == "donut":
            params["filter"] = "donut"
            print(f"  [VK] Собираю посты из VK Donut: {domain}...")
        else:
            print(f"  [VK] Собираю посты со стены: {domain}...")

        return await _get_wall(params)
