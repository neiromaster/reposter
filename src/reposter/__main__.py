import asyncio
import sys
from pathlib import Path

from .core.app_manager import AppManager
from .executors.binding_task_executor import BindingTaskExecutor
from .managers.telegram_manager import TelegramManager
from .managers.vk_manager import VKManager
from .managers.ytdlp_manager import YTDLPManager


async def main():
    try:
        if not Path("config.yaml").exists():
            raise FileNotFoundError("config.yaml не найден")

        ytdlp_manager = YTDLPManager()
        vk_manager = VKManager()
        telegram_manager = TelegramManager()

        task_executor = BindingTaskExecutor(
            vk_manager=vk_manager,
            telegram_manager=telegram_manager,
            ytdlp_manager=ytdlp_manager,
        )

        managers = [ytdlp_manager, vk_manager, telegram_manager]
        app = AppManager(managers=managers, task_executor=task_executor)

        await app.run()

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
