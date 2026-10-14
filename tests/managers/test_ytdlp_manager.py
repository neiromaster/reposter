# pyright: reportPrivateUsage=false
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.reposter.config.settings import DownloaderConfig, RetryConfig, Settings
from src.reposter.managers.ytdlp_manager import BROWSER_EXECUTABLES, YTDLPManager
from src.reposter.utils.browser import CookieSpec, ResolvedFirefoxProfile


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
    mock_settings.downloader.cookies_from_browser = "firefox:default-release-1"
    # cookie_spec is a @property: Mock(spec=) doesn't invoke getters, so set a real value.
    mock_settings.downloader.cookie_spec = CookieSpec(browser="firefox", profile="default-release-1")
    mock_settings.downloader.browser = "firefox"
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
async def test_restart_browser_unknown_browser_noop(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test restart_browser does nothing for an unsupported browser."""
    settings.downloader.cookie_spec = CookieSpec(browser="safari")
    ytdlp_manager._downloader_config = settings.downloader
    with patch("subprocess.Popen") as mock_popen:
        await ytdlp_manager.restart_browser()
    mock_popen.assert_not_called()


@pytest.mark.asyncio
async def test_restart_whole_browser_closes_gracefully(ytdlp_manager: YTDLPManager, settings: Settings):
    """Test whole-browser restart: graceful close before and after the refresh window."""
    settings.downloader.cookie_spec = CookieSpec(browser="chrome")
    settings.downloader.browser = "chrome"
    ytdlp_manager._downloader_config = settings.downloader

    proc = Mock()
    proc.info = {"name": BROWSER_EXECUTABLES["chrome"]}
    proc.cmdline.return_value = []
    proc.children.return_value = []
    proc.pid = 4242
    proc.wait = Mock()

    with (
        patch("psutil.process_iter", return_value=[proc]),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen") as mock_popen,
        patch("asyncio.sleep", AsyncMock()),
    ):
        await ytdlp_manager.restart_browser()

    assert mock_run.call_count == 2  # закрытие до и после окна обновления cookie
    assert mock_run.call_args.args[0] == ["taskkill", "/PID", "4242"]
    mock_popen.assert_called_once_with([BROWSER_EXECUTABLES["chrome"]])


@pytest.mark.asyncio
async def test_restart_firefox_profile_closes_only_matching(
    ytdlp_manager: YTDLPManager, settings: Settings, tmp_path: Path
):
    """Test profile restart: only the target profile instance is closed, launched with --profile."""
    settings.downloader.cookie_spec = CookieSpec(browser="firefox", profile="default-release-1")
    ytdlp_manager._downloader_config = settings.downloader
    resolved = ResolvedFirefoxProfile(
        path=tmp_path / "Profiles" / "ns5j57qn.default-release-1",
        name="default-release-1",
        is_default=False,
    )

    target = Mock()
    target.info = {"name": BROWSER_EXECUTABLES["firefox"]}
    target.cmdline.return_value = [r"C:\Program Files\Mozilla Firefox\firefox.exe", "-P", "default-release-1"]
    target.exe.return_value = r"C:\Program Files\Mozilla Firefox\firefox.exe"
    target.children.return_value = []
    target.pid = 111
    target.wait = Mock()

    other = Mock()
    other.info = {"name": BROWSER_EXECUTABLES["firefox"]}
    other.cmdline.return_value = [r"C:\Program Files\Mozilla Firefox\firefox.exe", "-P", "default-release-2"]
    other.children.return_value = []

    fake_ini = tmp_path / "profiles.ini"
    fake_ini.write_text(
        "[Profile0]\nName=default-release-1\nIsRelative=1\nPath=Profiles/ns5j57qn.default-release-1\n",
        encoding="utf-8",
    )

    with (
        patch("src.reposter.utils.browser._firefox_profiles_ini_paths", return_value=(fake_ini,)),
        patch("psutil.process_iter", return_value=[target, other]),
        patch("subprocess.run"),
        patch("subprocess.Popen") as mock_popen,
        patch("asyncio.sleep", AsyncMock()),
    ):
        await ytdlp_manager.restart_browser()

    mock_popen.assert_called_once_with(
        [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "--profile",
            str(resolved.path),
            "--allow-downgrade",
        ]
    )
    target.wait.assert_called()
    other.wait.assert_not_called()  # чужой профиль не тронут


@pytest.mark.asyncio
async def test_restart_falls_back_to_whole_browser_when_profile_unresolved(
    ytdlp_manager: YTDLPManager, settings: Settings, tmp_path: Path
):
    """Test fallback: unresolvable profile restarts the whole browser without flags."""
    settings.downloader.cookie_spec = CookieSpec(browser="firefox", profile="ghost-profile")
    ytdlp_manager._downloader_config = settings.downloader

    proc = Mock()
    proc.info = {"name": BROWSER_EXECUTABLES["firefox"]}
    proc.cmdline.return_value = []
    proc.children.return_value = []
    proc.pid = 111
    proc.wait = Mock()

    with (
        patch("src.reposter.utils.browser._firefox_profiles_ini_paths", return_value=(tmp_path / "missing.ini",)),
        patch("psutil.process_iter", return_value=[proc]),
        patch("subprocess.run"),
        patch("subprocess.Popen") as mock_popen,
        patch("asyncio.sleep", AsyncMock()),
    ):
        await ytdlp_manager.restart_browser()

    mock_popen.assert_called_once_with([BROWSER_EXECUTABLES["firefox"]])


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


class TestBuildYdlOpts:
    def test_uses_resolved_profile_tuple(self, ytdlp_manager: YTDLPManager, settings: Settings):
        settings.downloader.yt_dlp_opts = {"format": "best", "quiet": False}
        with patch(
            "src.reposter.managers.ytdlp_manager.resolve_cookie_profile",
            return_value=("firefox", r"C:\prof\ns5j57qn.default-release-1", None, None),
        ) as mock_resolve:
            opts = ytdlp_manager._build_ydl_opts(settings.downloader)
        assert opts["cookiesfrombrowser"] == ("firefox", r"C:\prof\ns5j57qn.default-release-1", None, None)
        assert opts["format"] == "best"
        assert opts["outtmpl"].startswith(str(Path(tempfile.gettempdir()) / "test_ytdlp"))
        assert opts["quiet"] is True
        assert opts["no_warnings"] is True
        assert opts["verbose"] is False
        mock_resolve.assert_called_once_with(settings.downloader.cookie_spec)

    def test_real_config_resolves_profile_path(self, ytdlp_manager: YTDLPManager, tmp_path: Path):
        ini = tmp_path / "profiles.ini"
        ini.write_text(
            "[Profile0]\nName=default-release-1\nIsRelative=1\nPath=Profiles/ns5j57qn.default-release-1\n",
            encoding="utf-8",
        )
        config = DownloaderConfig(cookies_from_browser="firefox:default-release-1", output_path=tmp_path / "dl")
        ytdlp_manager._downloader_config = config
        with patch("src.reposter.utils.browser._firefox_profiles_ini_paths", return_value=(ini,)):
            opts = ytdlp_manager._build_ydl_opts(config)
        assert opts["cookiesfrombrowser"] == (
            "firefox",
            str(tmp_path / "Profiles" / "ns5j57qn.default-release-1"),
            None,
            None,
        )

    def test_real_config_unresolvable_profile_passthrough(self, ytdlp_manager: YTDLPManager, tmp_path: Path):
        config = DownloaderConfig(cookies_from_browser="firefox:default-release-1", output_path=tmp_path / "dl")
        ytdlp_manager._downloader_config = config
        with patch("src.reposter.utils.browser._firefox_profiles_ini_paths", return_value=(tmp_path / "missing.ini",)):
            opts = ytdlp_manager._build_ydl_opts(config)
        assert opts["cookiesfrombrowser"] == ("firefox", "default-release-1", None, None)
