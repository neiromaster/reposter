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

                new_posts = [post for post in posts if post.id > last_post_id]

                if not new_posts:
                    log("✅ Новых постов нет.", indent=2)
                    continue

                log(f"📬 Найдено {len(new_posts)} новых постов. Начинаю обработку...", indent=2)
                new_posts.sort(key=lambda p: p.date)

                latest_post_id_in_batch = new_posts[-1].id

                prepared_posts: list[TelegramPost] = []
                for post in new_posts:
                    try:
                        log(f"⚙️ Обрабатываю пост {post.id}...", indent=3)
                        prepared_post = await self.post_processor.process_post(post)
                        prepared_posts.append(prepared_post)
                    except Exception as e:
                        log(f"❌ Не удалось обработать пост {post.id}: {e}", indent=3)

                # # Write to json file instead of printing
                # posts_as_dicts = [post.model_dump(mode="json") for post in new_posts]
                # async with aiofiles.open("new_posts.json", "w", encoding="utf-8") as f:
                #     await f.write(json.dumps(posts_as_dicts, indent=4, ensure_ascii=False))

                if not prepared_posts:
                    log("✅ Нет постов для публикации после обработки.", indent=2)
                    # Still update last_post_id to not re-process failed posts
                    await set_last_post_id(binding.vk.domain, latest_post_id_in_batch, settings.app.state_file)
                    continue

                log(f"✈️ Публикую в Telegram каналы: {binding.telegram.channel_ids}", indent=2)
                await self.telegram_manager.post_to_channels(binding.telegram, prepared_posts)

                await set_last_post_id(binding.vk.domain, latest_post_id_in_batch, settings.app.state_file)

                log(f"✅ Привязка {binding.vk.domain} обработана успешно.", indent=2)

            except Exception as e:
                log(f"❌ Ошибка при обработке привязки {binding.vk.domain}: {type(e).__name__}: {e}", indent=2)
