# pyright: reportPrivateUsage=false
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.reposter.config.settings import BoostyConfig, Settings
from src.reposter.exceptions import BoostyPublicationError
from src.reposter.managers.boosty_manager import BoostyManager
from src.reposter.models import PreparedPost, PreparedVideoAttachment


@pytest.fixture
async def boosty_manager():
    """Create a BoostyManager instance."""
    manager = BoostyManager()
    shutdown_event = asyncio.Event()
    manager.set_shutdown_event(shutdown_event)
    yield manager
    if manager._initialized:
        await manager.shutdown()


@pytest.fixture
def settings():
    """Create mock settings."""
    mock_settings = Mock(spec=Settings)
    return mock_settings


@pytest.fixture
def boosty_config():
    """Create a BoostyConfig instance."""
    config = BoostyConfig(blog_name="test_blog", subscription_level_id=123)
    return config


@pytest.mark.asyncio
async def test_init():
    """Test BoostyManager initialization."""
    # Arrange & Act
    manager = BoostyManager()

    # Assert
    assert manager._initialized is False
    assert manager._client is None
    assert manager._blog_name == ""
    assert manager._access_token is None
    assert manager._device_id is None
    assert manager._auth_path == "auth.json"


@pytest.mark.asyncio
async def test_set_shutdown_event(boosty_manager: BoostyManager):
    """Test set_shutdown_event method."""
    # Arrange
    event = asyncio.Event()

    # Act
    boosty_manager.set_shutdown_event(event)

    # Assert
    # The event should be set (we can't directly access _shutdown_event due to privacy)
    assert hasattr(boosty_manager, "_shutdown_event")


@pytest.mark.asyncio
async def test_setup_initializes_manager(boosty_manager: BoostyManager, settings: Settings):
    """Test that setup properly initializes the manager."""
    # Arrange & Act
    await boosty_manager.setup(settings)

    # Assert
    assert boosty_manager._initialized is True
    assert boosty_manager._client is not None
    assert isinstance(boosty_manager._client, httpx.AsyncClient)


@pytest.mark.asyncio
async def test_setup_already_initialized(boosty_manager: BoostyManager, settings: Settings):
    """Test setup when already initialized."""
    # Arrange
    await boosty_manager.setup(settings)
    initial_client = boosty_manager._client

    # Act
    with patch("src.reposter.managers.boosty_manager.log") as mock_log:
        await boosty_manager.setup(settings)

    # Assert
    assert boosty_manager._initialized is True
    assert boosty_manager._client is not None
    assert boosty_manager._client != initial_client  # Should be a new client
    # Should log restart message
    mock_log.assert_any_call("🚀 [Boosty] Клиент уже запущен. Перезапуск...", indent=1)


@pytest.mark.asyncio
async def test_authorize_missing_auth_file(boosty_manager: BoostyManager):
    """Test _authorize with missing auth file."""
    # Arrange
    blog_name = "test_blog"
    boosty_manager._auth_path = "nonexistent_auth.json"

    # Act & Assert
    with pytest.raises(FileNotFoundError):
        await boosty_manager._authorize(blog_name)


@pytest.mark.asyncio
async def test_authorize_success(boosty_manager: BoostyManager):
    """Test successful authorization."""
    # Arrange
    blog_name = "test_blog"

    # Create a temporary auth file
    auth_data = {
        "access_token": "test_token",
        "refresh_token": "test_refresh",
        "device_id": "test_device_id",
        "expires_in": 3600,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(auth_data, f)
        temp_auth_path = f.name

    boosty_manager._auth_path = temp_auth_path

    with patch("src.reposter.managers.boosty_manager.log") as mock_log:
        # Act
        await boosty_manager._authorize(blog_name)

        # Assert
        assert boosty_manager._access_token == "test_token"
        assert boosty_manager._device_id == "test_device_id"
        assert boosty_manager._blog_name == blog_name
        mock_log.assert_called_with("🔑 Авторизация успешна!", indent=4)

    # Clean up
    Path(temp_auth_path).unlink()


@pytest.mark.asyncio
async def test_authorize_missing_tokens(boosty_manager: BoostyManager):
    """Test _authorize with missing tokens in auth file."""
    # Arrange
    blog_name = "test_blog"

    # Create a temporary auth file with missing tokens
    auth_data = {"access_token": "", "refresh_token": "", "device_id": "", "expires_in": 0}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(auth_data, f)
        temp_auth_path = f.name

    boosty_manager._auth_path = temp_auth_path

    # Act & Assert
    with pytest.raises(Exception, match="access_token и device_id должны быть в файле auth.json"):
        await boosty_manager._authorize(blog_name)

    # Clean up
    Path(temp_auth_path).unlink()


@pytest.mark.asyncio
async def test_update_config_not_initialized(boosty_manager: BoostyManager, settings: Settings):
    """Test update_config when not initialized."""
    # Arrange
    with patch.object(boosty_manager, "setup", AsyncMock()) as mock_setup:
        # Act
        await boosty_manager.update_config(settings)

        # Assert
        mock_setup.assert_called_once_with(settings)


@pytest.mark.asyncio
async def test_update_config_initialized(boosty_manager: BoostyManager, settings: Settings):
    """Test update_config when already initialized."""
    # Arrange
    await boosty_manager.setup(settings)

    with patch("src.reposter.managers.boosty_manager.log") as mock_log:
        # Act
        await boosty_manager.update_config(settings)

        # Assert
        mock_log.assert_called_with("🚀 [Boosty] Конфигурация обновлена.", indent=1)


@pytest.mark.asyncio
async def test_shutdown_not_initialized(boosty_manager: BoostyManager):
    """Test shutdown when not initialized."""
    # Arrange - Don't initialize the manager

    # Act & Assert - Should not raise any exceptions
    await boosty_manager.shutdown()
    assert boosty_manager._initialized is False


@pytest.mark.asyncio
async def test_shutdown_initialized(boosty_manager: BoostyManager, settings: Settings):
    """Test shutdown when initialized."""
    # Arrange
    await boosty_manager.setup(settings)
    mock_client = Mock()
    mock_client.aclose = AsyncMock()
    boosty_manager._client = mock_client

    with patch("src.reposter.managers.boosty_manager.log") as mock_log:
        # Act
        await boosty_manager.shutdown()

        # Assert
        assert boosty_manager._initialized is False
        mock_client.aclose.assert_called_once()
        mock_log.assert_any_call("🚀 [Boosty] Завершение работы...", indent=1)
        mock_log.assert_any_call("🚀 [Boosty] Остановлен.", indent=1)


@pytest.mark.asyncio
async def test_async_context_manager(boosty_manager: BoostyManager, settings: Settings):
    """Test BoostyManager as an async context manager."""
    # Arrange
    await boosty_manager.setup(settings)
    mock_client = Mock()
    mock_client.aclose = AsyncMock()
    boosty_manager._client = mock_client

    # Act
    async with boosty_manager as manager:
        # Assert that we can enter the context
        assert manager is boosty_manager
        assert manager._initialized is True

    # Assert - Should have been shutdown correctly
    assert boosty_manager._initialized is False
    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_sleep_cancelable_no_shutdown(boosty_manager: BoostyManager):
    """Test _sleep_cancelable when no shutdown occurs."""
    # Arrange
    seconds = 1  # Integer sleep for testing

    # Act
    await boosty_manager._sleep_cancelable(seconds)

    # Assert - Should complete without throwing exceptions


@pytest.mark.asyncio
async def test_sleep_cancelable_with_shutdown(boosty_manager: BoostyManager):
    """Test _sleep_cancelable when shutdown occurs."""
    # Arrange
    if hasattr(boosty_manager, "_shutdown_event") and boosty_manager._shutdown_event:
        boosty_manager._shutdown_event.set()
    seconds = 1  # Integer value

    # Act
    await boosty_manager._sleep_cancelable(seconds)

    # Assert - Should complete without throwing exceptions


@pytest.mark.asyncio
async def test_upload_video_not_initialized(boosty_manager: BoostyManager):
    """Test upload_video when not initialized."""
    # Arrange
    video_path = "test_video.mp4"

    # Act & Assert
    with pytest.raises(RuntimeError, match="Boosty manager not initialized"):
        await boosty_manager.upload_video(video_path)


@pytest.mark.asyncio
async def test_upload_video_file_not_found(boosty_manager: BoostyManager, settings: Settings):
    """Test upload_video with non-existent file."""
    # Arrange
    await boosty_manager.setup(settings)
    video_path = "nonexistent_video.mp4"

    # Act & Assert
    with pytest.raises(FileNotFoundError):
        await boosty_manager.upload_video(video_path)


@pytest.mark.asyncio
async def test_upload_video_shutdown_during_upload(boosty_manager: BoostyManager, settings: Settings):
    """Test upload_video when shutdown occurs."""
    # Arrange
    await boosty_manager.setup(settings)
    if hasattr(boosty_manager, "_shutdown_event") and boosty_manager._shutdown_event:
        boosty_manager._shutdown_event.set()

    # Create a temporary video file
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"test video content")
        video_path = f.name

    # Act & Assert
    with pytest.raises(asyncio.CancelledError):
        await boosty_manager.upload_video(video_path)

    # Clean up
    Path(video_path).unlink()


@pytest.mark.asyncio
async def test_create_post_not_initialized(boosty_manager: BoostyManager, boosty_config: BoostyConfig):
    """Test create_post when not initialized."""
    # Arrange
    post = PreparedPost(text="Test post", attachments=[])

    # Act & Assert
    with pytest.raises(RuntimeError, match="Boosty manager not initialized"):
        await boosty_manager.create_post(boosty_config, post)


@pytest.mark.asyncio
async def test_create_post_no_video_attachments(
    boosty_manager: BoostyManager, settings: Settings, boosty_config: BoostyConfig
):
    """Test create_post with no video attachments."""
    # Arrange
    await boosty_manager.setup(settings)
    post = PreparedPost(text="Test post", attachments=[])

    with (
        patch.object(boosty_manager, "_authorize", new_callable=AsyncMock) as mock_authorize,
        patch("src.reposter.managers.boosty_manager.log") as mock_log,
    ):
        # Act
        results = await boosty_manager.create_post(boosty_config, post)

        # Assert
        assert results == []
        mock_authorize.assert_awaited_once_with(boosty_config.blog_name)
        mock_log.assert_called_with("📤 [Boosty] Нет видео для публикации, пост пропускается.", indent=4)


@pytest.mark.asyncio
async def test_check_shutdown_raises_cancelled_error(boosty_manager: BoostyManager):
    """Test that _check_shutdown raises CancelledError when shutdown event is set."""
    # Arrange
    if hasattr(boosty_manager, "_shutdown_event") and boosty_manager._shutdown_event:
        boosty_manager._shutdown_event.set()

    # Act & Assert
    with pytest.raises(asyncio.CancelledError):
        boosty_manager._check_shutdown()


@pytest.mark.asyncio
async def test_check_shutdown_no_exception(boosty_manager: BoostyManager):
    """Test that _check_shutdown does not raise exception when shutdown event is not set."""
    # Arrange - Don't set shutdown event

    # Act & Assert - Should not raise any exceptions
    boosty_manager._check_shutdown()


@pytest.mark.asyncio
async def test_health_check_success(boosty_manager: BoostyManager, settings: Settings):
    """Test health_check method with a successful response."""
    await boosty_manager.setup(settings)
    with patch.object(boosty_manager._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Mock(spec=httpx.Response, status_code=200)
        result = await boosty_manager.health_check()
        assert result == {"status": "ok"}
        mock_get.assert_awaited_once_with(boosty_manager.BASE_URL)


@pytest.mark.asyncio
async def test_health_check_failure(boosty_manager: BoostyManager, settings: Settings):
    """Test health_check method with a network error."""
    await boosty_manager.setup(settings)
    with patch.object(boosty_manager._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("Network error")
        result = await boosty_manager.health_check()
        assert result["status"] == "error"
        assert "Network error" in result["message"]


@pytest.mark.asyncio
async def test_health_check_not_initialized(boosty_manager: BoostyManager):
    """Test health_check when the manager is not initialized."""
    result = await boosty_manager.health_check()
    assert result == {"status": "error", "message": "BoostyManager not initialized"}


@pytest.mark.asyncio
async def test_make_request_with_retries_success(boosty_manager: BoostyManager, settings: Settings):
    """Test _make_request_with_retries succeeds on the first attempt."""
    await boosty_manager.setup(settings)
    with patch.object(boosty_manager._client, "request", new_callable=AsyncMock) as mock_request:
        mock_response = Mock(spec=httpx.Response, status_code=200)
        mock_request.return_value = mock_response
        response = await boosty_manager._make_request_with_retries("get", "http://test.com")
        assert response == mock_response
        mock_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_make_request_with_retries_retry_and_succeed(boosty_manager: BoostyManager, settings: Settings):
    """Test _make_request_with_retries retries on failure and then succeeds."""
    await boosty_manager.setup(settings)
    with (
        patch.object(boosty_manager._client, "request", new_callable=AsyncMock) as mock_request,
        patch.object(boosty_manager, "_sleep_cancelable", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_success_response = Mock(spec=httpx.Response, status_code=200)
        mock_request.side_effect = [httpx.RequestError("Network error"), mock_success_response]
        response = await boosty_manager._make_request_with_retries("get", "http://test.com", max_retries=2)
        assert response == mock_success_response
        assert mock_request.call_count == 2
        mock_sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_make_request_with_retries_all_fail(boosty_manager: BoostyManager, settings: Settings):
    """Test _make_request_with_retries fails after all retries."""
    await boosty_manager.setup(settings)
    with (
        patch.object(boosty_manager._client, "request", new_callable=AsyncMock) as mock_request,
        patch.object(boosty_manager, "_sleep_cancelable", new_callable=AsyncMock),
    ):
        mock_request.side_effect = httpx.RequestError("Network error")
        with pytest.raises(BoostyPublicationError):
            await boosty_manager._make_request_with_retries("get", "http://test.com", max_retries=2)
        assert mock_request.call_count == 2


@pytest.mark.asyncio
async def test_upload_video_success(boosty_manager: BoostyManager, settings: Settings):
    """Test successful video upload."""
    await boosty_manager.setup(settings)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"test video content")
        video_path = f.name

    prepare_response = {"uploadUrl": "http://test.com/upload", "id": "test_media_id"}
    finish_response = {"id": "final_video_id"}

    with (
        patch.object(boosty_manager, "_make_request_with_retries", new_callable=AsyncMock) as mock_make_request,
        patch("aiofiles.open") as mock_aiofiles,
        patch("os.path.getsize", return_value=100),
        patch("tqdm.tqdm"),
    ):
        # Simulate reading file in chunks
        mock_file = AsyncMock()
        mock_file.read.side_effect = [b"first chunk", b"second chunk", b""]
        mock_aiofiles.return_value.__aenter__.return_value = mock_file

        # Simulate API call responses
        mock_make_request.side_effect = [
            AsyncMock(spec=httpx.Response, json=lambda: prepare_response),
            AsyncMock(spec=httpx.Response, status_code=200),  # First chunk
            AsyncMock(spec=httpx.Response, status_code=200),  # Second chunk
            AsyncMock(spec=httpx.Response, json=lambda: finish_response),
        ]

        result = await boosty_manager.upload_video(video_path)

        assert result == finish_response
        assert mock_make_request.call_count == 4  # prepare, chunk1, chunk2, finish

    Path(video_path).unlink()


@pytest.mark.asyncio
async def test_create_post_success(boosty_manager: BoostyManager, settings: Settings, boosty_config: BoostyConfig):
    """Test successful post creation with simplified mocks."""
    await boosty_manager.setup(settings)

    attachment = PreparedVideoAttachment(
        file_path=Path("dummy.mp4"), filename="dummy.mp4", width=1920, height=1080, thumbnail_path=None
    )
    post = PreparedPost(text="Test post", attachments=[attachment], tags=["tag1"])

    mock_video_data: dict[str, Any] = {"id": "test_video_id"}
    mock_draft_response: dict[str, Any] = {}  # Empty response for draft creation is fine
    mock_publish_response: dict[str, Any] = {"data": {"post": {"id": "12345"}}}

    boosty_manager._blog_name = boosty_config.blog_name

    with (
        patch.object(boosty_manager, "_authorize", new_callable=AsyncMock),
        patch.object(boosty_manager, "upload_video", new_callable=AsyncMock, return_value=mock_video_data),
        patch.object(boosty_manager, "_make_request_with_retries", new_callable=AsyncMock) as mock_make_request,
    ):
        # Set up side effects for the two calls
        mock_make_request.side_effect = [
            AsyncMock(spec=httpx.Response, status_code=200, json=lambda: mock_draft_response),  # Draft creation
            AsyncMock(spec=httpx.Response, status_code=200, json=lambda: mock_publish_response),  # Publish
        ]

        results = await boosty_manager.create_post(boosty_config, post)

        assert len(results) == 1
        assert results[0] == mock_publish_response
        assert mock_make_request.await_count == 2

        # Verify the calls
        # First call: PUT to create draft
        first_call_args, first_call_kwargs = mock_make_request.await_args_list[0]
        assert first_call_args[0] == "put"
        assert f"/v1/blog/{boosty_config.blog_name}/post_draft" in first_call_args[1]
        assert "data" in first_call_kwargs

        # Second call: POST to publish
        second_call_args, second_call_kwargs = mock_make_request.await_args_list[1]
        assert second_call_args[0] == "post"
        assert f"/v1/blog/{boosty_config.blog_name}/publish/" in second_call_args[1]
        assert "data" not in second_call_kwargs
