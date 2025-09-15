from ..config.settings import Settings
from ..interfaces.task_executor import BaseTaskExecutor
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_manager import VKManager
from ..managers.ytdlp_manager import YTDLPManager
from ..utils.log import log


class BindingTaskExecutor(BaseTaskExecutor):
    """
    Implementation of business logic: processing VK → Telegram bindings.
    """

    def __init__(self, vk_manager: VKManager, telegram_manager: TelegramManager, ytdlp_manager: YTDLPManager):
        self.vk_manager = vk_manager
        self.telegram_manager = telegram_manager
        self.ytdlp_manager = ytdlp_manager

    async def execute(self, settings: Settings) -> None:
        log(f"📋 Обрабатываю {len(settings.bindings)} привязок...")

        for binding in settings.bindings:
            log(f"🔗 → Обрабатываю привязку: {binding.vk.domain} → {binding.telegram.channel_ids}", indent=1)

            try:
                posts = await self.vk_manager.get_vk_wall(
                    domain=binding.vk.domain,
                    post_count=binding.vk.post_count,
                    post_source=binding.vk.post_source,
                )

                print(posts)

                log("🎥 Скачиваю медиа (если есть)...", indent=2)
                # await self.ytdlp_manager.download_media(posts)

                log(f"✈️ Публикую в Telegram каналы: {binding.telegram.channel_ids}", indent=2)
                # await self.telegram_manager.post_to_channels(binding.telegram.channel_ids, posts)

                log(f"✅ Привязка {binding.vk.domain} обработана успешно.", indent=2)

            except Exception as e:
                log(f"❌ Ошибка при обработке привязки {binding.vk.domain}: {type(e).__name__}: {e}", indent=2)
