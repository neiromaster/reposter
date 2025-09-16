from ..config.settings import Settings
from ..core.post_processor import PostProcessor
from ..core.state_manager import get_last_post_id, set_last_post_id
from ..interfaces.task_executor import BaseTaskExecutor
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_manager import VKManager
from ..managers.ytdlp_manager import YTDLPManager
from ..models.dto import TelegramPost
from ..utils.log import log


class BindingTaskExecutor(BaseTaskExecutor):
    """
    Implementation of business logic: processing VK → Telegram bindings.
    """

    def __init__(
        self,
        vk_manager: VKManager,
        telegram_manager: TelegramManager,
        ytdlp_manager: YTDLPManager,
        post_processor: PostProcessor,
    ):
        self.vk_manager = vk_manager
        self.telegram_manager = telegram_manager
        self.ytdlp_manager = ytdlp_manager
        self.post_processor = post_processor

    async def execute(self, settings: Settings) -> None:
        log(f"📋 Обрабатываю {len(settings.bindings)} привязок...")

        for binding in settings.bindings:
            log(f"🔗 → Обрабатываю привязку: {binding.vk.domain} → {binding.telegram.channel_ids}", indent=1)

            try:
                last_post_id = await get_last_post_id(binding.vk.domain, settings.app.state_file)

                posts = await self.vk_manager.get_vk_wall(
                    domain=binding.vk.domain,
                    post_count=binding.vk.post_count,
                    post_source=binding.vk.post_source,
                )

                new_posts = sorted([post for post in posts if post.id > last_post_id], key=lambda p: p.date)

                if not new_posts:
                    log("✅ Новых постов нет.", indent=2)
                    continue

                log(f"📬 Найдено {len(new_posts)} новых постов. Начинаю последовательную обработку...", indent=2)

                for post in new_posts:
                    try:
                        log(f"⚙️ Обрабатываю пост {post.id}...", indent=3)
                        prepared_post = await self.post_processor.process_post(post)

                        if not prepared_post.attachments and not prepared_post.text:
                            log("⚠️ Пост пустой после обработки, пропускаю.", indent=4)
                            await set_last_post_id(binding.vk.domain, post.id, settings.app.state_file)
                            continue

                        log(f"✈️ Публикую пост {post.id} в Telegram каналы...", indent=3)
                        await self.telegram_manager.post_to_channels(binding.telegram, [prepared_post])

                        # Обновляем ID последнего успешно опубликованного поста
                        await set_last_post_id(binding.vk.domain, post.id, settings.app.state_file)
                        log(f"✅ Пост {post.id} успешно обработан и опубликован.", indent=4)

                    except Exception as e:
                        log(f"❌ Ошибка при обработке поста {post.id}: {e}. Пропускаю его.", indent=3)
                        # Не обновляем last_post_id, чтобы повторить попытку в следующий раз
                        continue

                log(f"✅ Привязка {binding.vk.domain} обработана.", indent=2)

            except Exception as e:
                log(f"❌ Критическая ошибка при получении постов для привязки {binding.vk.domain}: {e}", indent=2)
