import json
from asyncio import Event
from datetime import datetime
from pathlib import Path

import aiofiles

from ..config.settings import Settings
from ..core.post_processor import PostProcessor
from ..core.state_manager import get_last_post_id, set_last_post_id
from ..interfaces.task_executor import BaseTaskExecutor
from ..managers.boosty_manager import BoostyManager
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_manager import VKManager
from ..managers.ytdlp_manager import YTDLPManager
from ..models.dto import Post as VkPost
from ..utils.cleaner import delete_files_async
from ..utils.log import log

NEW_POSTS_FILE = Path("new_posts.json")


async def save_new_posts_to_json(posts: list[VkPost], file_path: Path) -> None:
    """Saves a list of VkPost objects to a JSON file."""
    try:
        # Convert VkPost objects to dictionaries for JSON serialization
        posts_data = [post.model_dump(mode="json") for post in posts]
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(posts_data, ensure_ascii=False, indent=4))
        log(f"💾 Сохранено {len(posts)} новых постов в {file_path}", indent=2)
    except Exception as e:
        log(f"❌ Ошибка при сохранении новых постов в JSON: {e}", indent=2)


class BindingTaskExecutor(BaseTaskExecutor):
    """
    Implementation of business logic: processing VK → Telegram/Boosty bindings.
    """

    def __init__(
        self,
        vk_manager: VKManager,
        telegram_manager: TelegramManager,
        ytdlp_manager: YTDLPManager,
        post_processor: PostProcessor,
        boosty_manager: BoostyManager | None = None,
        debug: bool = False,
    ):
        self.vk_manager = vk_manager
        self.telegram_manager = telegram_manager
        self.ytdlp_manager = ytdlp_manager
        self.post_processor = post_processor
        self.boosty_manager = boosty_manager
        self.debug = debug
        self._shutdown_event: Event | None = None

    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event."""
        self._shutdown_event = event

    async def execute(self, settings: Settings) -> None:
        log(f"📋 Обрабатываю {len(settings.bindings)} привязок...")

        for binding in settings.bindings:
            if self._shutdown_event and self._shutdown_event.is_set():
                log("⏹️  Остановка — прерываю обработку привязок.", indent=1)
                break

            target_descriptions: list[str] = []
            if binding.telegram:
                target_descriptions.append(f"Telegram: {binding.telegram.channel_ids}")
            if binding.boosty:
                target_descriptions.append(f"Boosty: {binding.boosty.blog_name}")

            target_description = " и ".join(target_descriptions) if target_descriptions else "Unknown"

            log(
                f"🔄 {datetime.now().strftime('%H:%M:%S %Y-%m-%d')} "
                f"Обрабатываю привязку: {binding.vk.domain} → {target_description}",
                padding_top=1,
            )

            try:
                last_post_id = await get_last_post_id(
                    binding.vk.domain, binding.vk.post_source, settings.app.state_file
                )

                posts = await self.vk_manager.get_vk_wall(
                    domain=binding.vk.domain,
                    post_count=binding.vk.post_count,
                    post_source=binding.vk.post_source,
                )

                new_posts = sorted([post for post in posts if post.id > last_post_id], key=lambda p: p.date)

                if not new_posts:
                    log("✅ Новых постов нет.", indent=2)
                    continue

                if self.debug:
                    await save_new_posts_to_json(new_posts, NEW_POSTS_FILE)

                log(f"📬 Найдено {len(new_posts)} новых постов. Начинаю последовательную обработку...", indent=2)

                for post in new_posts:
                    if self._shutdown_event and self._shutdown_event.is_set():
                        log("⏹️  Остановка — прерываю обработку постов.", indent=3)
                        break

                    try:
                        log(f"⚙️ Обрабатываю пост {post.id}...", indent=3, padding_top=1)
                        prepared_post = await self.post_processor.process_post(post)

                        if not prepared_post.attachments and not prepared_post.text:
                            log("⚠️ Пост пустой после обработки, пропускаю.", indent=4)
                            await set_last_post_id(
                                binding.vk.domain, post.id, binding.vk.post_source, settings.app.state_file
                            )
                            continue

                        if binding.telegram:
                            log(f"✈️ Публикую пост {post.id} в Telegram каналы...", indent=3, padding_top=1)
                            await self.telegram_manager.post_to_channels(binding.telegram, [prepared_post])

                        if binding.boosty and self.boosty_manager:
                            log(
                                f"🚀 Публикую пост {post.id} в Boosty блог {binding.boosty.blog_name}...",
                                indent=3,
                                padding_top=1,
                            )
                            await self.boosty_manager.create_post(binding.boosty, prepared_post)

                        await delete_files_async(prepared_post.attachments)

                        await set_last_post_id(
                            binding.vk.domain, post.id, binding.vk.post_source, settings.app.state_file
                        )
                        log(f"✅ Пост {post.id} успешно обработан и опубликован.", indent=4)

                    except Exception as e:
                        log(
                            f"❌ Ошибка при обработке поста {post.id}: {e}. "
                            f"Прерываю обработку привязки {binding.vk.domain}.",
                            indent=3,
                        )
                        break

                else:
                    log(f"✅ Привязка {binding.vk.domain} обработана.", indent=2)

            except Exception as e:
                log(f"❌ Критическая ошибка при получении постов для привязки {binding.vk.domain}: {e}", indent=2)
