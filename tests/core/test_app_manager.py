# type: ignore[reportPrivateUsage]
import asyncio
import signal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.core.app_manager import AppManager
from src.reposter.interfaces.base_manager import BaseManager
from src.reposter.interfaces.task_executor import BaseTaskExecutor


@pytest.fixture
def mock_managers() -> list[AsyncMock]:
    """Fixture for mocking managers."""
    return [AsyncMock(spec=BaseManager), AsyncMock(spec=BaseManager)]


@pytest.fixture
def mock_task_executor() -> AsyncMock:
    """Fixture for mocking the task executor."""
    return AsyncMock(spec=BaseTaskExecutor)


@pytest.fixture
def mock_settings_manager() -> MagicMock:
    """Fixture for mocking the settings manager."""
    return MagicMock()


@pytest.fixture
def app_manager(
    mock_managers: list[BaseManager],
    mock_task_executor: BaseTaskExecutor,
    mock_settings_manager: MagicMock,
) -> AppManager:
    """Fixture for creating an AppManager instance."""
    manager = AppManager(mock_managers, mock_task_executor)
    manager._settings_manager = mock_settings_manager
    mock_settings_manager.get_settings.return_value.app.wait_time_seconds = 0.1
    return manager


@pytest.mark.asyncio
async def test_execute_task_success(
    app_manager: AppManager, mock_task_executor: AsyncMock, mock_settings_manager: MagicMock
):
    """Test successful task execution."""
    # Arrange
    mock_settings_manager.get_settings.return_value = MagicMock()

    # Act
    await app_manager._execute_task()

    # Assert
    mock_task_executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_task_cancelled(app_manager: AppManager, mock_task_executor: AsyncMock):
    """Test task execution when cancelled."""
    # Arrange
    mock_task_executor.execute.side_effect = asyncio.CancelledError()

    # Act & Assert
    # Should not raise any exception
    await app_manager._execute_task()


@pytest.mark.asyncio
async def test_execute_task_exception(app_manager: AppManager, mock_task_executor: AsyncMock):
    """Test task execution with an exception."""
    # Arrange
    mock_task_executor.execute.side_effect = Exception("Test exception")

    # Act & Assert
    # Should not raise any exception
    await app_manager._execute_task()


@pytest.mark.asyncio
async def test_input_watcher_enter(app_manager: AppManager):
    """Test the input watcher when Enter is pressed."""

    # Arrange
    async def side_effect(*args: Any, **kwargs: Any) -> None:
        app_manager._force_run_event.set()
        raise asyncio.CancelledError()

    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = side_effect

        # Act
        await app_manager._input_watcher()

        # Assert
        mock_ainput.assert_awaited_once()
        assert app_manager._force_run_event.is_set()


@pytest.mark.asyncio
async def test_input_watcher_eof(app_manager: AppManager):
    """Test the input watcher with EOFError."""
    # Arrange
    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = EOFError()

        # Act & Assert
        # Should not raise any exception
        await app_manager._input_watcher()


@pytest.mark.asyncio
async def test_periodic_wrapper_runs_once(app_manager: AppManager, mock_task_executor: AsyncMock):
    """Test that the periodic wrapper runs a task and then stops."""

    # Arrange
    async def side_effect(*args: Any, **kwargs: Any) -> None:
        app_manager._stop_app_event.set()

    mock_task_executor.execute.side_effect = side_effect

    # Act
    await app_manager._periodic_wrapper()

    # Assert
    mock_task_executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_periodic_wrapper_force_run(app_manager: AppManager, mock_task_executor: AsyncMock):
    """Test that the periodic wrapper is interrupted by the force run event."""
    # Arrange
    counter = 0

    async def side_effect(*args: Any, **kwargs: Any) -> None:
        nonlocal counter
        counter += 1
        if counter > 1:
            app_manager._stop_app_event.set()
        else:
            app_manager._force_run_event.set()

    mock_task_executor.execute.side_effect = side_effect

    # Act
    await app_manager._periodic_wrapper()

    # Assert
    assert mock_task_executor.execute.await_count == 2


@pytest.mark.asyncio
async def test_run(app_manager: AppManager, mock_managers: list[AsyncMock], mock_task_executor: AsyncMock):
    """Test the main run method."""

    # Arrange
    async def stop_app(*args: Any, **kwargs: Any) -> None:
        app_manager._stop_app_event.set()

    # Stop the app after the first periodic wrap
    app_manager._periodic_wrapper = AsyncMock(side_effect=stop_app)

    # Act
    await app_manager.run()

    # Assert
    for manager in mock_managers:
        manager.set_shutdown_event.assert_called_once()
        manager.setup.assert_awaited_once()
        manager.update_config.assert_awaited_once()

    mock_task_executor.set_shutdown_event.assert_called_once()
    app_manager._periodic_wrapper.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_with_signal(app_manager: AppManager):
    """Test that the run method is stopped by a signal."""
    # Arrange
    with patch("signal.signal") as mock_signal, patch("asyncio.get_running_loop") as mock_get_loop:
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        # Act
        app_manager._setup_signal_handlers()

        # Assert
        assert mock_signal.call_count >= 1

        # Simulate a signal
        app_manager._shutdown_handler(signal.SIGINT, None)
        mock_loop.call_soon_threadsafe.assert_called_once_with(app_manager._stop_app_event.set)
