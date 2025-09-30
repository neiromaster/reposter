# type: ignore[reportPrivateUsage]
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.reposter.core.app_manager import AppManager
from src.reposter.core.event_system import (
    AppStartEvent,
    AppStopEvent,
    EventManager,
    HealthCheckRequestEvent,
    TaskExecutionCompleteEvent,
    TaskExecutionRequestEvent,
    UserInputReceivedEvent,
)
from src.reposter.interfaces.base_manager import BaseManager
from src.reposter.interfaces.task_executor import BaseTaskExecutor
from src.reposter.managers.boosty_manager import BoostyManager
from src.reposter.managers.telegram_manager import TelegramManager
from src.reposter.managers.vk_manager import VKManager


@pytest.fixture
def mock_managers() -> list[AsyncMock]:
    """Fixture for mocking managers."""
    return [
        AsyncMock(spec=VKManager),
        AsyncMock(spec=TelegramManager),
        AsyncMock(spec=BoostyManager),
    ]


@pytest.fixture
def mock_task_executor() -> AsyncMock:
    """Fixture for mocking the task executor."""
    return AsyncMock(spec=BaseTaskExecutor)


@pytest.fixture
def mock_settings_manager() -> MagicMock:
    """Fixture for mocking the settings manager."""
    return MagicMock()


@pytest.fixture
def mock_event_manager() -> AsyncMock:
    """Fixture for mocking the event manager."""
    return AsyncMock(spec=EventManager)


@pytest.fixture
def app_manager(
    mock_managers: list[BaseManager],
    mock_task_executor: BaseTaskExecutor,
    mock_settings_manager: MagicMock,
    mock_event_manager: AsyncMock,
) -> AppManager:
    """Fixture for creating an AppManager instance."""
    manager = AppManager(mock_managers, mock_task_executor, mock_event_manager)
    manager._settings_manager = mock_settings_manager
    mock_settings_manager.get_settings.return_value.app.wait_time_seconds = 0.1
    return manager


@pytest.mark.asyncio
async def test_run_emits_app_start_and_stop_events(
    app_manager: AppManager,
    mock_managers: list[AsyncMock],
    mock_task_executor: AsyncMock,
    mock_event_manager: AsyncMock,
):
    """Test the main run method emits start and stop events."""

    # Arrange
    async def stop_app(*args: Any, **kwargs: Any) -> None:
        app_manager._stop_app_event.set()

    for manager in mock_managers:
        manager.__aenter__ = AsyncMock(return_value=manager)
        manager.__aexit__ = AsyncMock(return_value=None)

    original_run = app_manager._periodic_task_scheduler

    async def stop_after_setup(*args: Any, **kwargs: Any) -> None:
        app_manager._stop_app_event.set()
        await original_run()

    app_manager._periodic_task_scheduler = AsyncMock(side_effect=stop_after_setup)

    # Act
    await app_manager.run()

    # Assert
    assert any(isinstance(call.args[0], AppStartEvent) for call in mock_event_manager.emit.await_args_list)
    assert any(isinstance(call.args[0], AppStopEvent) for call in mock_event_manager.emit.await_args_list)

    for manager in mock_managers:
        manager.set_shutdown_event.assert_called_once()
        manager.setup.assert_awaited_once()
        manager.update_config.assert_awaited_once()

    mock_task_executor.set_shutdown_event.assert_called_once()


@pytest.mark.asyncio
async def test_input_watcher_emits_user_input_event(app_manager: AppManager, mock_event_manager: AsyncMock):
    """Test the input watcher emits user input events."""
    # Arrange
    input_text = "test command"

    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = [input_text, asyncio.CancelledError()]  # Stop after one input

        # Act
        await app_manager._input_watcher()

        # Assert
        assert mock_ainput.await_count == 2
        mock_event_manager.emit.assert_awaited_once()
        emitted_event = mock_event_manager.emit.await_args.args[0]
        assert isinstance(emitted_event, UserInputReceivedEvent)
        assert emitted_event.data.get("command") == input_text


@pytest.mark.asyncio
async def test_input_watcher_health_command_emits_health_event(app_manager: AppManager, mock_event_manager: AsyncMock):
    """Test the input watcher for health command emits health check event."""
    # Arrange
    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = ["health", asyncio.CancelledError()]  # Stop after one input

        # Act
        await app_manager._input_watcher()

        # Assert
        mock_event_manager.emit.assert_awaited_once()
        emitted_event = mock_event_manager.emit.await_args.args[0]
        assert isinstance(emitted_event, UserInputReceivedEvent)


@pytest.mark.asyncio
async def test_handle_task_execution_request_calls_executor(
    app_manager: AppManager, mock_task_executor: AsyncMock, mock_settings_manager: MagicMock
):
    """Test the task execution request handler calls the task executor."""
    # Arrange
    mock_settings_manager.get_settings.return_value = MagicMock()

    # Act
    event = TaskExecutionRequestEvent()
    await app_manager._handle_task_execution_request(event)

    # Assert
    mock_task_executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_periodic_task_scheduler_emits_task_execution_event(
    app_manager: AppManager, mock_event_manager: AsyncMock
):
    """Test the periodic task scheduler emits task execution events."""
    # Arrange
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = lambda _: app_manager._stop_app_event.set()

        # Act
        await app_manager._periodic_task_scheduler()

        # Assert
        mock_event_manager.emit.assert_awaited_once()
        emitted_event = mock_event_manager.emit.await_args.args[0]
        assert isinstance(emitted_event, TaskExecutionRequestEvent)


@pytest.mark.asyncio
async def test_handle_user_input_health_emits_health_event(app_manager: AppManager, mock_event_manager: AsyncMock):
    """Test that health command in user input handler emits health check event."""
    # Act
    event = UserInputReceivedEvent("health")
    await app_manager._handle_user_input(event)

    # Assert
    mock_event_manager.emit.assert_awaited_once()
    emitted_event = mock_event_manager.emit.await_args.args[0]
    assert isinstance(emitted_event, HealthCheckRequestEvent)


@pytest.mark.asyncio
async def test_handle_user_input_force_execution(app_manager: AppManager, mock_event_manager: AsyncMock):
    """Test that non-health command in user input handler emits task execution event."""
    # Act
    event = UserInputReceivedEvent("any_other_command")
    await app_manager._handle_user_input(event)

    # Assert
    mock_event_manager.emit.assert_awaited_once()
    emitted_event = mock_event_manager.emit.await_args.args[0]
    assert isinstance(emitted_event, TaskExecutionRequestEvent)
    assert emitted_event.data.get("force") is True


@pytest.mark.asyncio
async def test_handle_task_execution_cancelled(
    app_manager: AppManager, mock_task_executor: AsyncMock, mock_event_manager: AsyncMock
):
    """Test the task execution handler when the task is cancelled."""
    # Arrange
    mock_task_executor.execute.side_effect = asyncio.CancelledError()

    # Act
    event = TaskExecutionRequestEvent()
    await app_manager._handle_task_execution_request(event)

    # Assert
    mock_event_manager.emit.assert_awaited_once()
    emitted_event = mock_event_manager.emit.await_args.args[0]
    assert isinstance(emitted_event, TaskExecutionCompleteEvent)
    assert not emitted_event.data["success"]
    assert emitted_event.data["error"] == "Cancelled"


@pytest.mark.asyncio
async def test_handle_task_execution_exception(
    app_manager: AppManager, mock_task_executor: AsyncMock, mock_event_manager: AsyncMock
):
    """Test the task execution handler with an exception."""
    # Arrange
    mock_task_executor.execute.side_effect = Exception("Test error")

    # Act
    event = TaskExecutionRequestEvent()
    await app_manager._handle_task_execution_request(event)

    # Assert
    mock_event_manager.emit.assert_awaited_once()
    emitted_event = mock_event_manager.emit.await_args.args[0]
    assert isinstance(emitted_event, TaskExecutionCompleteEvent)
    assert not emitted_event.data["success"]
    assert emitted_event.data["error"] == "Test error"


@pytest.mark.asyncio
async def test_input_watcher_exception(app_manager: AppManager):
    """Test the input watcher with an unexpected exception."""
    with (
        patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput,
        patch("src.reposter.core.app_manager.log") as mock_log,
    ):
        mock_ainput.side_effect = [Exception("Test exception"), asyncio.CancelledError()]

        await app_manager._input_watcher()

        mock_log.assert_any_call("⚠️ Ошибка в input_watcher: Exception: Test exception")


@pytest.mark.asyncio
async def test_periodic_task_scheduler_exception(app_manager: AppManager):
    """Test the periodic task scheduler with an exception."""
    with (
        patch.object(app_manager, "_event_manager", new=AsyncMock()) as mock_event_manager,
        patch("src.reposter.core.app_manager.log") as mock_log,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_event_manager.emit.side_effect = Exception("Test exception")
        mock_sleep.side_effect = lambda _: app_manager._stop_app_event.set()

        await app_manager._periodic_task_scheduler()

        mock_log.assert_any_call("⚠️ Ошибка в планировщике периодических задач: Exception: Test exception")


def test_shutdown_handler(app_manager: AppManager):
    """Test the shutdown handler sets the stop event."""
    with patch("asyncio.get_running_loop") as mock_get_loop:
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        app_manager._shutdown_handler(0, None)

        mock_loop.call_soon_threadsafe.assert_called_once_with(app_manager._stop_app_event.set)


@pytest.mark.asyncio
async def test_run_registers_health_checks(app_manager: AppManager, mock_managers: list[AsyncMock]):
    """Test that the run method registers health checks for all managers."""
    # Arrange
    app_manager._periodic_task_scheduler = AsyncMock(side_effect=lambda: app_manager._stop_app_event.set())
    for manager in mock_managers:
        manager.__aenter__ = AsyncMock(return_value=manager)
        manager.__aexit__ = AsyncMock(return_value=None)

    with patch.object(app_manager, "_health_monitor") as mock_health_monitor:
        # Act
        await app_manager.run()

        # Assert
        assert mock_health_monitor.register_check.call_count == len(mock_managers)
        mock_health_monitor.register_check.assert_has_calls(
            [
                call("VK", mock_managers[0].health_check),
                call("Telegram", mock_managers[1].health_check),
                call("Boosty", mock_managers[2].health_check),
            ]
        )


@pytest.mark.asyncio
async def test_handle_health_check_request(app_manager: AppManager):
    """Test the health check request handler."""
    with (
        patch.object(app_manager, "_health_monitor", new=AsyncMock()) as mock_health_monitor,
        patch("src.reposter.core.app_manager.log") as mock_log,
    ):
        mock_health_monitor.check_health.return_value = {
            "VK": {"status": "ok", "message": "OK"},
            "Telegram": {"status": "error", "message": "Failed"},
        }

        await app_manager._handle_health_check_request(HealthCheckRequestEvent())

        mock_health_monitor.check_health.assert_awaited_once()
        mock_log.assert_any_call("  - VK: OK (OK)")
        mock_log.assert_any_call("  - Telegram: ERROR (Failed)")
