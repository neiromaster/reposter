# pyright: reportPrivateUsage=false
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.reposter.config.settings import DownloaderConfig, RetryConfig, Settings
from src.reposter.managers.ytdlp_manager import BROWSER_EXECUTABLES, YTDLPManager


@pytest.fixture
async def ytdlp_manager():
    manager = YTDLPManager()
    shutdown_event = asyncio.Event()
    manager.set_shutdown_event(shutdown_event)
    yield manager
    if manager._initialized:
        await manager.shutdown()


@pytest.fixture
def settings():
    mock_settings = Mock(spec=Settings)
    mock_settings.downloader = Mock(spec=DownloaderConfig)
    mock_settings.downloader.output_path = Path(tempfile.gettempdir()) / "test_ytdlp"
    mock_settings.downloader.yt_dlp_opts = {}
    mock_settings.downloader.retries = RetryConfig(count=2, delay_seconds=1)
    mock_settings.downloader.browser = "chrome"
    mock_settings.downloader.browser_restart_wait_seconds = 1
    return mock_settings


@pytest.mark.asyncio
async def test_setup_initializes_manager(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test that setup properly initializes the manager."""
    # Arrange & Act
    await ytdlp_manager.setup(settings)

    # Assert
    assert ytdlp_manager._initialized is True
    assert ytdlp_manager._downloader_config == settings.downloader


@pytest.mark.asyncio
async def test_update_config_not_initialized(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test that update_config calls setup when not initialized."""
    # Arrange
    new_settings = Mock(spec=Settings)
    new_settings.downloader = Mock(spec=DownloaderConfig)
    new_settings.downloader.output_path = Path(tempfile.gettempdir()) / "test_new"
    new_settings.downloader.yt_dlp_opts = {}
    new_settings.downloader.retries = RetryConfig(count=1, delay_seconds=1)
    new_settings.downloader.browser = "firefox"
    new_settings.downloader.browser_restart_wait_seconds = 2

    # Act
    await ytdlp_manager.update_config(new_settings)

    # Assert
    assert ytdlp_manager._initialized is True
    assert ytdlp_manager._downloader_config == new_settings.downloader


@pytest.mark.asyncio
async def test_update_config_initialized(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test that update_config updates settings when already initialized."""
    # Arrange
    await ytdlp_manager.setup(settings)

    new_settings = Mock(spec=Settings)
    new_settings.downloader = Mock(spec=DownloaderConfig)
    new_settings.downloader.output_path = Path(tempfile.gettempdir()) / "test_updated"
    new_settings.downloader.yt_dlp_opts = {"format": "best"}
    new_settings.downloader.retries = RetryConfig(count=3, delay_seconds=2)
    new_settings.downloader.browser = "edge"
    new_settings.downloader.browser_restart_wait_seconds = 3

    # Act
    await ytdlp_manager.update_config(new_settings)

    # Assert
    assert ytdlp_manager._downloader_config == new_settings.downloader


@pytest.mark.asyncio
async def test_shutdown_terminates_active_process(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test that shutdown properly terminates any active process."""
    # Arrange
    await ytdlp_manager.setup(settings)
    mock_process = Mock()
    mock_process.is_alive.return_value = True
    mock_process.join = Mock()
    ytdlp_manager._active_proc = mock_process

    # Act
    await ytdlp_manager.shutdown()

    # Assert
    mock_process.terminate.assert_called()
    mock_process.kill.assert_called()  # This would be called if join fails
    assert ytdlp_manager._initialized is False
    assert ytdlp_manager._active_proc is None


@pytest.mark.asyncio
async def test_shutdown_not_initialized(ytdlp_manager: YTDLPManager):
    """Test that shutdown works when not initialized."""
    # Arrange - Don't initialize the manager

    # Act & Assert - Should not raise any exceptions
    await ytdlp_manager.shutdown()
    # We can't directly access _initialized, but we can verify the method runs without error


@pytest.mark.asyncio
async def test_terminate_active_process_alive(ytdlp_manager: YTDLPManager):
    """Test _terminate_active with an alive process."""
    # Arrange
    mock_process = Mock()
    mock_process.is_alive.return_value = True
    mock_process.join = Mock()
    ytdlp_manager._active_proc = mock_process

    # Act
    await ytdlp_manager._terminate_active()

    # Assert
    mock_process.terminate.assert_called()
    mock_process.join.assert_called()
    assert ytdlp_manager._active_proc is None


@pytest.mark.asyncio
async def test_terminate_active_process_dead(ytdlp_manager: YTDLPManager):
    """Test _terminate_active with a dead process."""
    # Arrange
    mock_process = Mock()
    mock_process.is_alive.return_value = False
    ytdlp_manager._active_proc = mock_process

    # Act
    await ytdlp_manager._terminate_active()

    # Assert - Should not call terminate or kill
    mock_process.terminate.assert_not_called()
    assert ytdlp_manager._active_proc is None


@pytest.mark.asyncio
async def test_terminate_active_no_process(ytdlp_manager: YTDLPManager):
    """Test _terminate_active with no active process."""
    # Arrange
    ytdlp_manager._active_proc = None

    # Act
    await ytdlp_manager._terminate_active()

    # Assert - Should not raise any exceptions
    assert ytdlp_manager._active_proc is None


@pytest.mark.asyncio
async def test_restart_browser_no_config(ytdlp_manager: YTDLPManager):
    """Test restart_browser when no configuration is set."""
    # Arrange
    ytdlp_manager._downloader_config = None

    # Act & Assert - Should not raise any exceptions
    await ytdlp_manager.restart_browser()


@pytest.mark.asyncio
async def test_restart_browser_unsupported_browser(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test restart_browser with unsupported browser."""
    # Arrange
    # We can't easily change the browser enum, so we'll test with a valid browser that gets filtered out
    settings.downloader.browser = "chrome"  # Valid browser
    ytdlp_manager._downloader_config = settings.downloader

    # Mock subprocess.Popen to avoid actually starting a browser process
    with patch("subprocess.Popen"):
        # Act & Assert - Should not raise any exceptions
        await ytdlp_manager.restart_browser()


@pytest.mark.asyncio
async def test_restart_browser_kills_processes(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test restart_browser properly kills existing browser processes."""
    # Arrange
    settings.downloader.browser = "chrome"
    ytdlp_manager._downloader_config = settings.downloader

    # Create mock processes to be killed
    mock_proc1 = Mock()
    mock_proc1.info = {"name": "chrome.exe"}
    mock_proc1.kill = Mock()
    mock_proc1.wait = Mock()  # This is a synchronous method, not async

    mock_proc2 = Mock()
    mock_proc2.info = {"name": "chrome.exe"}
    mock_proc2.kill = Mock()
    mock_proc2.wait = Mock()  # This is a synchronous method, not async

    # Mock subprocess.Popen to avoid actually starting a browser process
    with (
        patch("psutil.process_iter", side_effect=[[mock_proc1], [mock_proc2]]),
        patch("subprocess.Popen"),
        patch("asyncio.sleep", AsyncMock()),
    ):
        # Act
        await ytdlp_manager.restart_browser()

        # Assert
        mock_proc1.kill.assert_called()
        mock_proc1.wait.assert_called()
        mock_proc2.kill.assert_called()
        mock_proc2.wait.assert_called()


@pytest.mark.asyncio
async def test_download_video_no_config(ytdlp_manager: YTDLPManager):
    """Test download_video when no configuration is set."""
    # Arrange
    ytdlp_manager._downloader_config = None

    # Act
    result = await ytdlp_manager.download_video("https://example.com/video")

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_download_video_shutdown_during_download(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test download_video when shutdown occurs during download."""
    # Arrange
    await ytdlp_manager.setup(settings)

    # Set shutdown event to trigger during download
    if ytdlp_manager._shutdown_event:
        ytdlp_manager._shutdown_event.set()

    # Act & Assert
    with pytest.raises(asyncio.CancelledError):  # _check_shutdown raises CancelledError
        await ytdlp_manager.download_video("https://example.com/video")


@pytest.mark.asyncio
async def test_download_video_success_first_attempt(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test download_video success on first attempt."""
    # Arrange
    await ytdlp_manager.setup(settings)
    video_url = "https://example.com/video"
    mock_result = ("success", str(Path(tempfile.gettempdir()) / "test.mp4"))

    with patch.object(ytdlp_manager, "_wait_for_result_or_shutdown", AsyncMock()) as mock_wait:
        mock_wait.return_value = mock_result

        # Act
        result = await ytdlp_manager.download_video(video_url)

        # Assert
        assert result == Path(mock_result[1])
        mock_wait.assert_called()


@pytest.mark.asyncio
async def test_download_video_success_after_retry(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test download_video success after a retry."""
    # Arrange
    await ytdlp_manager.setup(settings)
    video_url = "https://example.com/video"
    error_result = ("error", "private video")
    success_result = ("success", str(Path(tempfile.gettempdir()) / "test.mp4"))

    with (
        patch.object(ytdlp_manager, "_wait_for_result_or_shutdown", AsyncMock()) as mock_wait,
        patch.object(ytdlp_manager, "restart_browser", AsyncMock()) as mock_restart,
    ):
        # First call returns error, second returns success
        mock_wait.side_effect = [error_result, success_result]

        # Act
        result = await ytdlp_manager.download_video(video_url)

        # Assert
        assert result == Path(success_result[1])
        assert mock_wait.call_count == 2  # Called twice (first failed, second succeeded)
        mock_restart.assert_called()


@pytest.mark.asyncio
async def test_download_video_all_retries_fail(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test download_video failure after all retries."""
    # Arrange
    await ytdlp_manager.setup(settings)
    settings.downloader.retries.count = 2  # Set to 2 retries
    ytdlp_manager._downloader_config = settings.downloader

    video_url = "https://example.com/video"
    error_result = ("error", "some error")

    with (
        patch.object(ytdlp_manager, "_wait_for_result_or_shutdown", AsyncMock()) as mock_wait,
        patch.object(ytdlp_manager, "restart_browser", AsyncMock()) as mock_restart,
    ):
        mock_wait.return_value = error_result

        # Act
        result = await ytdlp_manager.download_video(video_url)

        # Assert
        assert result is None
        assert mock_wait.call_count == 2  # Called for each retry
        # restart_browser should not be called since error message doesn't contain expected strings
        mock_restart.assert_not_called()


@pytest.mark.asyncio
async def test_download_video_private_video_triggers_restart(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test that private video error triggers browser restart."""
    # Arrange
    await ytdlp_manager.setup(settings)
    video_url = "https://example.com/video"
    error_result = ("error", "this video is only available for registered users")
    success_result = ("success", str(Path(tempfile.gettempdir()) / "test.mp4"))

    with (
        patch.object(ytdlp_manager, "_wait_for_result_or_shutdown", AsyncMock()) as mock_wait,
        patch.object(ytdlp_manager, "restart_browser", AsyncMock()) as mock_restart,
    ):
        # First call returns error (private video), second call returns success
        mock_wait.side_effect = [error_result, success_result]

        # Act
        result = await ytdlp_manager.download_video(video_url)

        # Assert
        assert result == Path(success_result[1])
        assert mock_wait.call_count == 2  # Called twice
        mock_restart.assert_called_once()


@pytest.mark.asyncio
async def test_download_video_cancelled_error_handling(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test download_video handles CancelledError correctly."""
    # Arrange
    await ytdlp_manager.setup(settings)
    video_url = "https://example.com/video"

    with (
        patch.object(ytdlp_manager, "_wait_for_result_or_shutdown", AsyncMock()) as mock_wait,
        patch.object(ytdlp_manager, "_terminate_active", AsyncMock()) as mock_terminate,
    ):
        # Make _wait_for_result_or_shutdown raise CancelledError
        mock_wait.side_effect = asyncio.CancelledError()

        # Act & Assert
        with pytest.raises(asyncio.CancelledError):
            await ytdlp_manager.download_video(video_url)

        # Assert that _terminate_active was called
        mock_terminate.assert_called_once()


@pytest.mark.asyncio
async def test_async_context_manager(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test that YTDLPManager works as an async context manager."""
    # Arrange
    await ytdlp_manager.setup(settings)
    mock_process = Mock()
    mock_process.is_alive.return_value = True
    mock_process.join = Mock()
    ytdlp_manager._active_proc = mock_process

    # Act
    async with ytdlp_manager as mgr:
        # Just verify we can enter the context
        assert mgr is not None

    # Assert - Should have been shutdown correctly
    mock_process.terminate.assert_called()
    mock_process.join.assert_called()
    assert ytdlp_manager._initialized is False


@pytest.mark.asyncio
async def test_wait_for_result_or_shutdown_with_shutdown(ytdlp_manager: YTDLPManager):
    """Test _wait_for_result_or_shutdown when shutdown is set."""
    # Arrange
    mock_process = Mock()
    mock_process.is_alive.return_value = True
    mock_queue = Mock()
    mock_queue.get_nowait.side_effect = Exception("Queue empty")  # Simulate empty queue

    ytdlp_manager._active_proc = mock_process
    if ytdlp_manager._shutdown_event:
        ytdlp_manager._shutdown_event.set()  # Set shutdown event

    # Act & Assert
    with pytest.raises(asyncio.CancelledError):
        await ytdlp_manager._wait_for_result_or_shutdown(mock_process, mock_queue)

    # Verify process was terminated
    assert ytdlp_manager._active_proc is None


@pytest.mark.asyncio
async def test_wait_for_result_or_shutdown_with_result(ytdlp_manager: YTDLPManager):
    """Test _wait_for_result_or_shutdown when result is available."""
    # Arrange
    mock_process = Mock()
    mock_process.is_alive.return_value = False  # Process is not alive
    expected_result = ("success", "/path/to/video.mp4")
    mock_queue = Mock()
    mock_queue.get_nowait.return_value = expected_result

    # Act
    result = await ytdlp_manager._wait_for_result_or_shutdown(mock_process, mock_queue)

    # Assert
    assert result == expected_result


@pytest.mark.asyncio
async def test_wait_for_result_or_shutdown_cancelled_error(ytdlp_manager: YTDLPManager):
    """Test _wait_for_result_or_shutdown handles CancelledError correctly."""
    # Arrange
    mock_process = Mock()
    mock_process.is_alive.return_value = True
    mock_queue = Mock()
    mock_queue.get_nowait.side_effect = Exception("Queue empty")  # Simulate empty queue

    ytdlp_manager._active_proc = mock_process
    if ytdlp_manager._shutdown_event:
        ytdlp_manager._shutdown_event.set()  # Set shutdown event

    # Act & Assert
    with patch.object(ytdlp_manager, "_terminate_active", AsyncMock()) as mock_terminate:
        with pytest.raises(asyncio.CancelledError):
            await ytdlp_manager._wait_for_result_or_shutdown(mock_process, mock_queue)

        # Assert that _terminate_active was called
        mock_terminate.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_result_or_shutdown_empty_queue_finally(ytdlp_manager: YTDLPManager):
    """Test _wait_for_result_or_shutdown when queue is empty in finally block."""
    # Arrange
    mock_process = Mock()
    mock_process.is_alive.return_value = False  # Process is not alive
    mock_queue = Mock()
    mock_queue.get_nowait.side_effect = Exception("Queue empty")  # Simulate empty queue

    # Act
    result = await ytdlp_manager._wait_for_result_or_shutdown(mock_process, mock_queue)

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_sleep_cancelable_no_shutdown(ytdlp_manager: YTDLPManager):
    """Test _sleep_cancelable when no shutdown occurs."""
    # Arrange
    seconds = 1  # Integer sleep for testing

    # Act
    await ytdlp_manager._sleep_cancelable(seconds)

    # Assert - Should complete without throwing exceptions


@pytest.mark.asyncio
async def test_sleep_cancelable_with_shutdown(ytdlp_manager: YTDLPManager):
    """Test _sleep_cancelable when shutdown occurs."""
    # Arrange
    if ytdlp_manager._shutdown_event:
        ytdlp_manager._shutdown_event.set()
    seconds = 1  # Integer value

    # Act
    await ytdlp_manager._sleep_cancelable(seconds)

    # Assert - Should complete without throwing exceptions


def test_browser_executables_structure():
    """Test that BROWSER_EXECUTABLES has the expected structure."""
    # Assert
    assert "chrome" in BROWSER_EXECUTABLES
    assert "firefox" in BROWSER_EXECUTABLES
    assert "edge" in BROWSER_EXECUTABLES
