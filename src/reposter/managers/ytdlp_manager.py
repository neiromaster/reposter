from types import TracebackType
from typing import Any

from ..config.settings import Settings
from ..interfaces.base_manager import BaseManager


class YTDLPManager(BaseManager):
    def __init__(self):
        self._initialized = False
        self._download_path: str = ""
        self._options: dict[str, Any] = {}

    async def setup(self, settings: Settings) -> None:
        print("🎥 [YTDLP] Инициализация yt-dlp...")
        self._download_path = str(settings.downloader.output_path)
        self._options = settings.downloader.yt_dlp_opts
        # Здесь можно инициализировать кэш, создать директории и т.д.
        self._initialized = True
        print(f"🎥 [YTDLP] Готов к работе. Путь: {self._download_path}")

    async def update_config(self, settings: Settings) -> None:
        if not self._initialized:
            await self.setup(settings)
            return

        old_path = self._download_path
        old_opts = self._options.copy()

        self._download_path = str(settings.downloader.output_path)
        self._options = settings.downloader.yt_dlp_opts

        print("🎥 [YTDLP] Конфиг обновлён:")
        if old_path != self._download_path:
            print(f"   Путь изменён: {old_path} → {self._download_path}")
        if old_opts != self._options:
            print("   Опции yt-dlp обновлены")

    async def shutdown(self) -> None:
        print("🎥 [YTDLP] Завершение работы...")
        # close sessions, save cache, etc.
        self._initialized = False

    async def __aenter__(self) -> "YTDLPManager":
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
