from asyncio import Event
from types import TracebackType
from typing import Any

from ..config.settings import Settings
from ..interfaces.base_manager import BaseManager


class TelegramManager(BaseManager):
    def __init__(self):
        self._initialized = False
        self._client: Any = None
        self._api_id: int = 0
        self._api_hash: str = ""
        self._shutdown_event: Event | None = None

    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event from the AppManager."""
        self._shutdown_event = event

    async def setup(self, settings: Settings) -> None:
        print("✈️ [Telegram] Инициализация Telegram клиента...")
        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash
        # self._client = kurigram.Client(...)
        # await self._client.start()
        self._initialized = True
        print("✈️ [Telegram] Клиент готов.")

    async def update_config(self, settings: Settings) -> None:
        if not self._initialized:
            await self.setup(settings)
            return

        old_id = self._api_id
        old_hash = self._api_hash

        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash

        if old_id != self._api_id or old_hash != self._api_hash:
            print("✈️ [Telegram] API ключи изменились — требуется перезапуск клиента.")
            # await self.shutdown()
            # await self.setup(settings)
        else:
            print("✈️ [Telegram] Конфиг обновлён, ключи не изменились.")

    async def shutdown(self) -> None:
        print("✈️ [Telegram] Завершение работы...")
        # if self._client: await self._client.stop()
        self._initialized = False

    async def __aenter__(self) -> "TelegramManager":
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
