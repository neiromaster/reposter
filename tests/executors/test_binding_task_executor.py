# pyright: reportPrivateUsage=false
from asyncio import Event
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from _pytest.logging import LogCaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from src.reposter.config.settings import (
    AppConfig,
    Settings,
)
from src.reposter.config.settings import (
    BindingConfig as Binding,
)
from src.reposter.config.settings import (
    BoostyConfig as BoostyTarget,
)
from src.reposter.config.settings import (
    TelegramConfig as TelegramTarget,
)
from src.reposter.config.settings import (
    VKConfig as VKSource,
)
from src.reposter.executors.binding_task_executor import BindingTaskExecutor, save_new_posts_to_json
from src.reposter.managers.boosty_manager import BoostyManager
from src.reposter.managers.telegram_manager import TelegramManager
from src.reposter.managers.vk_manager import VKManager
from src.reposter.managers.ytdlp_manager import YTDLPManager
from src.reposter.models.dto import Post, PreparedPost
from src.reposter.processing.post_processor import PostProcessor


class TestBindingTaskExecutor:
    @pytest.fixture
    def mock_vk_manager(self) -> AsyncMock:
        return AsyncMock(spec=VKManager)

    @pytest.fixture
    def mock_telegram_manager(self) -> AsyncMock:
        return AsyncMock(spec=TelegramManager)

    @pytest.fixture
    def mock_ytdlp_manager(self) -> AsyncMock:
        return AsyncMock(spec=YTDLPManager)

    @pytest.fixture
    def mock_post_processor(self) -> AsyncMock:
        return AsyncMock(spec=PostProcessor)

    @pytest.fixture
    def mock_boosty_manager(self) -> AsyncMock:
        return AsyncMock(spec=BoostyManager)

    @pytest.fixture
    def binding_task_executor(
        self,
        mock_vk_manager: AsyncMock,
        mock_telegram_manager: AsyncMock,
        mock_ytdlp_manager: AsyncMock,
        mock_post_processor: AsyncMock,
        mock_boosty_manager: AsyncMock,
    ) -> BindingTaskExecutor:
        return BindingTaskExecutor(
            vk_manager=mock_vk_manager,
            telegram_manager=mock_telegram_manager,
            ytdlp_manager=mock_ytdlp_manager,
            post_processor=mock_post_processor,
            boosty_manager=mock_boosty_manager,
            debug=False,
        )

    @pytest.mark.asyncio
    async def test_execute_with_bindings(self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch):
        """Test execute with bindings."""
        # Mock environment variables
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")

        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        # Create sample posts
        old_post = Post(id=1, text="old", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None)
        new_post = Post(id=2, text="new", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None)

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch("src.reposter.executors.binding_task_executor.set_last_post_id") as mock_set_last_post_id,
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
        ):
            mock_get_vk_wall.return_value = [old_post, new_post]
            prepared_post = PreparedPost(text="processed", attachments=[])
            mock_process_post.return_value = prepared_post

            # Execute
            await binding_task_executor.execute(settings)

            # Verify that only the new post was processed (the old one should be skipped)
            mock_process_post.assert_called_once_with(new_post)

            # Verify that set_last_post_id was called to mark the new post as processed
            mock_set_last_post_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_shutdown_event_set(
        self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch
    ):
        """Test execute with shutdown event already set."""
        # Mock environment variables
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")

        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        shutdown_event = Event()
        shutdown_event.set()  # Set the event to trigger shutdown
        binding_task_executor.set_shutdown_event(shutdown_event)

        with patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall:
            await binding_task_executor.execute(settings)

            # Verify that no manager methods were called due to shutdown
            mock_get_vk_wall.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_new_posts(self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch):
        settings = Settings.load()
        settings.app = AppConfig(state_file=Path("test_state.yaml"))
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        # Create sample posts
        old_post = Post(id=1, text="old", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None)
        new_post = Post(id=2, text="new", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None)

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch("src.reposter.executors.binding_task_executor.set_last_post_id") as mock_set_last_post_id,
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
        ):
            mock_get_vk_wall.return_value = [old_post, new_post]
            prepared_post = PreparedPost(text="processed", attachments=[])
            mock_process_post.return_value = prepared_post

            # Execute
            await binding_task_executor.execute(settings)

            # Verify that only the new post was processed
            mock_process_post.assert_called_once_with(new_post)

            # Verify that set_last_post_id was called to mark the new post as processed
            mock_set_last_post_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_boosty_target(
        self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch
    ):
        """Test execute with both Telegram and Boosty targets."""
        # Mock environment variables
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")

        settings = Settings.load()
        settings.app = AppConfig(state_file=Path("test_state.yaml"))
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
                boosty=BoostyTarget(blog_name="test_blog", subscription_level_id=1),
            )
        ]

        # Create sample posts
        new_post = Post(id=2, text="new", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None)

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch("src.reposter.executors.binding_task_executor.set_last_post_id"),
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
            patch.object(binding_task_executor.telegram_manager, "post_to_channels") as mock_post_to_channels,
            patch.object(binding_task_executor.boosty_manager, "create_post") as mock_create_post,
        ):
            mock_get_vk_wall.return_value = [new_post]
            prepared_post = PreparedPost(text="processed", attachments=[])
            mock_process_post.return_value = prepared_post

            # Execute
            await binding_task_executor.execute(settings)

            # Verify both managers were called
            mock_post_to_channels.assert_called_once()
            mock_create_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_empty_post_after_processing(
        self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch
    ):
        """Test execute when a post becomes empty after processing."""
        # Mock environment variables
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")

        settings = Settings.load()
        settings.app = AppConfig(state_file=Path("test_state.yaml"))
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        # Create sample post
        new_post = Post(id=2, text="new", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None)

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch("src.reposter.executors.binding_task_executor.set_last_post_id"),
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
            patch.object(binding_task_executor.telegram_manager, "post_to_channels") as mock_post_to_channels,
        ):
            mock_get_vk_wall.return_value = [new_post]
            empty_post = PreparedPost(text="", attachments=[])
            mock_process_post.return_value = empty_post

            # Execute
            await binding_task_executor.execute(settings)

            # Verify that the telegram manager was not called since post is empty
            mock_post_to_channels.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_shutdown_event(self, binding_task_executor: BindingTaskExecutor):
        """Test setting the shutdown event."""
        event = Event()
        binding_task_executor.set_shutdown_event(event)
        assert binding_task_executor._shutdown_event is event

    @pytest.mark.asyncio
    async def test_execute_no_new_posts(self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch):
        """Test execute when there are no new posts."""
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
        ):
            mock_get_vk_wall.return_value = [
                Post(id=1, text="old", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None)
            ]
            await binding_task_executor.execute(settings)
            mock_process_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_shutdown_during_post_processing(
        self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch
    ):
        """Test execute with shutdown during post processing."""
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        shutdown_event = Event()
        binding_task_executor.set_shutdown_event(shutdown_event)

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
        ):
            mock_get_vk_wall.return_value = [
                Post(id=2, text="new1", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None),
                Post(id=3, text="new2", date=3000, attachments=[], owner_id=1, from_id=1, is_pinned=None),
            ]

            def side_effect(*args: Any, **kwargs: Any) -> PreparedPost:
                shutdown_event.set()
                return PreparedPost(text="processed", attachments=[])

            mock_process_post.side_effect = side_effect

            await binding_task_executor.execute(settings)
            mock_process_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_post_processing_fails(
        self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch
    ):
        """Test execute when post processing fails."""
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
            patch.object(binding_task_executor.telegram_manager, "post_to_channels") as mock_post_to_channels,
        ):
            mock_get_vk_wall.return_value = [
                Post(id=2, text="new", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None)
            ]
            mock_process_post.side_effect = Exception("Processing error")

            await binding_task_executor.execute(settings)
            mock_post_to_channels.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_debug_mode(self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch):
        """Test execute in debug mode."""
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]
        binding_task_executor.debug = True

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch("src.reposter.executors.binding_task_executor.save_new_posts_to_json") as mock_save_json,
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
        ):
            mock_get_vk_wall.return_value = [
                Post(id=2, text="new", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None)
            ]
            await binding_task_executor.execute(settings)
            mock_save_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_get_posts_fails(self, binding_task_executor: BindingTaskExecutor, monkeypatch: MonkeyPatch):
        """Test execute when getting posts fails."""
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        settings = Settings.load()
        settings.bindings = [
            Binding(
                vk=VKSource(domain="test", post_count=5, post_source="wall"),
                telegram=TelegramTarget(channel_ids=[123]),
            )
        ]

        with (
            patch("src.reposter.executors.binding_task_executor.get_last_post_id", return_value=1),
            patch.object(binding_task_executor.vk_manager, "get_vk_wall") as mock_get_vk_wall,
            patch.object(binding_task_executor.post_processor, "process_post") as mock_process_post,
        ):
            mock_get_vk_wall.side_effect = Exception("VK error")
            await binding_task_executor.execute(settings)
            mock_process_post.assert_not_called()


class TestSaveNewPostsToJson:
    @pytest.mark.asyncio
    async def test_save_new_posts_to_json_success(self, tmp_path: Path):
        """Test saving posts to JSON file successfully."""
        posts = [
            Post(id=1, text="test1", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None),
            Post(id=2, text="test2", date=2000, attachments=[], owner_id=1, from_id=1, is_pinned=None),
        ]
        file_path = tmp_path / "test_posts.json"

        with patch("src.reposter.executors.binding_task_executor.aiofiles.open"):
            await save_new_posts_to_json(posts, file_path)
            # The function should complete without error

    @pytest.mark.asyncio
    async def test_save_new_posts_to_json_exception(self, tmp_path: Path, caplog: LogCaptureFixture):
        """Test saving posts to JSON when an exception occurs."""
        posts = [Post(id=1, text="test1", date=1000, attachments=[], owner_id=1, from_id=1, is_pinned=None)]
        file_path = tmp_path / "test_posts.json"

        with (
            patch("src.reposter.executors.binding_task_executor.aiofiles.open", side_effect=Exception("File error")),
            patch("src.reposter.executors.binding_task_executor.log") as mock_log,
        ):
            await save_new_posts_to_json(posts, file_path)
            # Verify that an error was logged
            mock_log.assert_called()
