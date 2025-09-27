from ..executors.binding_task_executor import BindingTaskExecutor
from ..interfaces.app_composer import AppComposer
from ..interfaces.app_manager import BaseAppManager
from ..managers.boosty_manager import BoostyManager
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_manager import VKManager
from ..managers.ytdlp_manager import YTDLPManager
from ..processing.post_processor import PostProcessor
from ..processing.steps import (
    AttachmentDownloaderStep,
    AttachmentDtoCreationStep,
    LinkNormalizationStep,
    TagExtractionStep,
)
from .app_manager import AppManager


class DefaultAppComposer(AppComposer):
    def compose_app(self, debug: bool = False) -> BaseAppManager:
        ytdlp_manager = YTDLPManager()
        vk_manager = VKManager()
        telegram_manager = TelegramManager()
        boosty_manager = BoostyManager()

        processing_steps = [
            LinkNormalizationStep(),
            TagExtractionStep(),
            AttachmentDownloaderStep(
                vk_manager=vk_manager,
                ytdlp_manager=ytdlp_manager,
            ),
            AttachmentDtoCreationStep(),
        ]

        post_processor = PostProcessor(steps=processing_steps)

        task_executor = BindingTaskExecutor(
            vk_manager=vk_manager,
            telegram_manager=telegram_manager,
            ytdlp_manager=ytdlp_manager,
            post_processor=post_processor,
            boosty_manager=boosty_manager,
            debug=debug,
        )

        managers = [ytdlp_manager, vk_manager, telegram_manager, boosty_manager]
        return AppManager(managers=managers, task_executor=task_executor)
