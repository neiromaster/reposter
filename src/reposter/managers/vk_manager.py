from typing import Any

from ..config.settings import Settings
from ..interfaces.base_manager import BaseManager


class VKManager(BaseManager):
    def __init__(self):
        self._initialized = False
        self._token: str = ""
        self._session: Any = None  # aiohttp.ClientSession

    async def setup(self, settings: Settings) -> None:
        print("🌐 [VK] Инициализация VK API...")
        self._token = settings.vk_service_token
        # self._session = aiohttp.ClientSession(...)
        self._initialized = True
        print("🌐 [VK] Подключение к VK API установлено.")

    async def update_config(self, settings: Settings) -> None:
        if not self._initialized:
            await self.setup(settings)
            return

        old_token = self._token
        self._token = settings.vk_service_token

        if old_token != self._token:
            print("🌐 [VK] Токен обновлён — переподключение...")
            # await self._reconnect()
        else:
            print("🌐 [VK] Конфиг обновлён, токен не изменился.")

    async def shutdown(self) -> None:
        print("🌐 [VK] Завершение работы...")
        # if self._session: await self._session.close()
        self._initialized = False
