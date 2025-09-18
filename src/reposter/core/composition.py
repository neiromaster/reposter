from ..executors.binding_task_executor import BindingTaskExecutor
from ..interfaces.app_composer import AppComposer
from ..interfaces.app_manager import BaseAppManager
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_user_manager import VKUserManager
from ..managers.ytdlp_manager import YTDLPManager
from .app_manager import AppManager
from .post_processor import PostProcessor


class DefaultAppComposer(AppComposer):
    def compose_app(self, debug: bool = False) -> BaseAppManager:
        ytdlp_manager = YTDLPManager()
        vk_manager = VKUserManager()
        telegram_manager = TelegramManager()

        post_processor = PostProcessor(
            vk_manager=vk_manager,
            ytdlp_manager=ytdlp_manager,
        )

        task_executor = BindingTaskExecutor(
            vk_manager=vk_manager,
            telegram_manager=telegram_manager,
            ytdlp_manager=ytdlp_manager,
            post_processor=post_processor,
            debug=debug,
        )

        managers = [ytdlp_manager, vk_manager, telegram_manager]
        return AppManager(managers=managers, task_executor=task_executor)
