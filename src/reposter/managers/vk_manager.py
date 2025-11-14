from __future__ import annotations

import asyncio
from asyncio import Event
from pathlib import Path
from types import TracebackType
from typing import Any, final

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
from ..exceptions import VKApiError
from ..interfaces.base_manager import BaseManager
from ..models import Post, VKAPIResponseDict, WallGetResponse
from ..utils.log import log


class VKManager(BaseManager):
    def __init__(self) -> None:
        super().__init__()
        self._initialized: bool = False
        self._service_token: str = ""
        self._user_token: str = ""
        self._client: httpx.AsyncClient | None = None

    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event from the AppManager."""
        super().set_shutdown_event(event)

    async def setup(self, settings: Settings) -> None:
        """Initializes the VK user manager and the HTTP client."""
        if self._initialized:
            log("🌐 [VK] Клиент уже запущен. Перезапуск...", indent=1)
            await self.shutdown()

        log("🌐 [VK] Запуск...", indent=1)

        self._user_token = settings.vk_user_token or ""
        self._service_token = settings.vk_service_token

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            http2=True,
            headers={"User-Agent": "Reposter/1.0"},
            follow_redirects=True,
        )
        self._initialized = True
        log("🌐 [VK] Готов к работе.", indent=1)

    async def update_config(self, settings: Settings) -> None:
        """Handles configuration updates."""
        if not self._initialized:
            await self.setup(settings)
            return

        if self._user_token == settings.vk_user_token and self._service_token == settings.vk_service_token:
            log("🌐 [VK] Конфигурация обновлена, без изменений.", indent=1)
            return

        log("🌐 [VK] Конфигурация изменилась, перезапуск...", indent=1)
        await self.shutdown()
        await self.setup(settings)

    async def shutdown(self) -> None:
        """Initiates shutdown and closes the client."""
        if not self._initialized:
            return
        log("🌐 [VK] Завершение работы...", indent=1)
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._initialized = False
        log("🌐 [VK] Остановлен.", indent=1)

    async def __aenter__(self) -> VKManager:
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

    @final
    async def _should_retry(self, retry_state: RetryCallState) -> bool:
        """Return True if the exception is retryable and shutdown is not requested."""
        if self._shutdown_event and self._shutdown_event.is_set():
            return False

        if not retry_state.outcome:
            return False
        exc = retry_state.outcome.exception()

        if isinstance(exc, VKApiError):
            return False

        if isinstance(exc, asyncio.CancelledError):
            return False
        return isinstance(exc, (httpx.RequestError | httpx.HTTPStatusError | RuntimeError))

    @final
    async def _before_sleep(self, retry_state: RetryCallState) -> None:
        """Log before sleeping."""
        if retry_state.outcome and retry_state.next_action:
            log(
                f"❌ [VK] Ошибка: {retry_state.outcome.exception()}. "
                f"Повтор через {retry_state.next_action.sleep:.2f} c...",
                indent=1,
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
            if self._client is None:
                raise RuntimeError("Client not initialized. Call setup() first.")
            if not url.path or url.path == "/":
                log(f"⚠️ [VK] URL не содержит пути для сохранения: {url}", indent=1)
                return None

            save_path = download_path / Path(url.path).name
            save_path.parent.mkdir(exist_ok=True, parents=True)

            try:
                async with self._client.stream("GET", str(url)) as resp:
                    resp.raise_for_status()
                    async with await anyio.open_file(save_path, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            self._check_shutdown()
                            await f.write(chunk)
                log(f"✅ [VK] Файл сохранён: {save_path.name}", indent=5)
                return save_path

            except asyncio.CancelledError:
                if save_path.exists():
                    save_path.unlink()
                log("⏹️ [VK] Загрузка файла прервана.", indent=1)
                raise

            except Exception:
                if save_path.exists():
                    save_path.unlink()
                raise

        return await _download()

    async def health_check(self) -> dict[str, Any]:
        """Performs a health check of the VK API."""
        if not self._initialized or not self._client:
            return {"status": "error", "message": "VKManager not initialized"}

        log("🩺 [VK] Проверка состояния...", indent=1)
        try:
            params = {
                "owner_id": -1,  # A valid public group, e.g., VK Testers
                "count": 0,
                "access_token": self._service_token,
                "v": "5.199",
            }
            resp = await self._client.get("https://api.vk.ru/method/wall.get", params=params)
            resp.raise_for_status()
            data: VKAPIResponseDict = resp.json()

            if "error" in data:
                log(f"🩺 [VK] Ошибка: {data['error']['error_msg']}", indent=1)
                return {"status": "error", "message": data["error"]["error_msg"]}

            log("🩺 [VK] OK", indent=1)
            return {"status": "ok"}
        except Exception as e:
            log(f"🩺 [VK] Ошибка: {e}", indent=1)
            return {"status": "error", "message": str(e)}

    async def get_vk_wall(self, domain: str, page_size: int, post_source: str, last_post_id: int | None) -> list[Post]:
        """Requests posts from a VK wall (or Donut) with retry and cancellation."""

        @retry(
            wait=wait_exponential(multiplier=2, min=2, max=10),
            stop=stop_after_attempt(3),
            retry=self._should_retry,
            before_sleep=self._before_sleep,
            retry_error_cls=RetryError,
        )
        async def _get_wall_posts_page(params: dict[str, Any]) -> list[Post]:
            if self._client is None:
                raise RuntimeError("Client not initialized. Call setup() first.")

            resp = await self._client.get("https://api.vk.ru/method/wall.get", params=params)
            resp.raise_for_status()
            data: VKAPIResponseDict = resp.json()

            if "error" in data:
                raise VKApiError(f"VK API Error: {data['error']['error_msg']}")

            response_data = data.get("response")
            if not response_data:
                raise ValueError("VK API response is empty or invalid.")

            return WallGetResponse.model_validate(response_data).items

        async def _get_all_new_posts(base_params: dict[str, Any]) -> list[Post]:
            all_new_posts: list[Post] = []
            offset = 0
            while True:
                self._check_shutdown()
                params = {**base_params, "offset": offset, "count": page_size}
                page_posts = await _get_wall_posts_page(params)

                if not page_posts:
                    break

                if last_post_id is None:
                    all_new_posts.extend(page_posts)
                    break

                found_old_post = False
                for post in page_posts:
                    if post.id <= last_post_id:
                        found_old_post = True
                    else:
                        all_new_posts.append(post)

                if found_old_post:
                    break

                offset += page_size

                if offset > 2000:
                    log(
                        f"⚠️ [VK] Достигнут лимит пагинации ({offset=}). Прерываю, чтобы избежать бесконечного цикла.",
                        indent=1,
                    )
                    break

            return [post for post in all_new_posts if last_post_id is None or post.id > last_post_id]

        if post_source == "donut":
            if not self._user_token:
                raise ValueError("User token is required for donut posts.")

            log(f"🔍 [VK] Собираю посты из VK Donut: {domain}...", indent=1)
            params = {
                "domain": domain,
                "access_token": self._user_token,
                "v": "5.199",
                "filter": "donut",
            }
            return await _get_all_new_posts(params)

        # post_source == "wall"
        if self._user_token:
            log(f"🔍 [VK] Собираю посты со стены (с фильтрацией Donut): {domain}...", indent=1)
            base_params = {
                "domain": domain,
                "access_token": self._user_token,
                "v": "5.199",
            }

            all_posts = await _get_all_new_posts({**base_params, "filter": "all"})

            try:
                donut_posts = await _get_all_new_posts({**base_params, "filter": "donut"})
                donut_ids = {p.id for p in donut_posts}
                return [post for post in all_posts if post.id not in donut_ids]
            except (VKApiError, ValueError) as e:
                if "no access to donuts" in str(e):
                    log(
                        "⚠️ [VK] Нет доступа к донатным постам, невозможно отфильтровать. "
                        "Возвращаются все посты со стены.",
                        indent=1,
                    )
                    return all_posts
                else:
                    raise
        else:
            # service token only
            log(f"🔍 [VK] Собираю посты со стены: {domain}...", indent=1)
            params = {
                "domain": domain,
                "access_token": self._service_token,
                "v": "5.199",
            }
            return await _get_all_new_posts(params)
