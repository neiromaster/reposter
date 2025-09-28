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


@pytest.fixture(autouse=True)
def mock_log_fixture() -> MagicMock:
    """Fixture for mocking log."""
    with patch("src.reposter.core.app_manager.log") as mock_log:
        yield mock_log


@pytest.mark.asyncio
async def test_execute_task_exception_when_stopped(
    app_manager: AppManager, mock_task_executor: AsyncMock, mock_log_fixture: MagicMock
):
    """Test that exception in task is not logged when app is stopped."""
    # Arrange
    app_manager._stop_app_event.set()
    mock_task_executor.execute.side_effect = Exception("Test exception")

    # Act
    await app_manager._execute_task()

    # Assert
    mock_log_fixture.assert_not_called()


@pytest.mark.asyncio
async def test_input_watcher_exception(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test the input watcher with an unexpected exception."""
    # Arrange
    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = [Exception("Test exception"), asyncio.CancelledError()]

        # Act
        await app_manager._input_watcher()

        # Assert
        mock_log_fixture.assert_any_call("⚠️ Ошибка в input_watcher: Exception: Test exception")


@pytest.mark.asyncio
async def test_input_watcher_exception_when_stopped(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test that exception in input watcher is not logged when app is stopped."""
    # Arrange
    app_manager._stop_app_event.set()
    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = Exception("Test exception")

        # Act
        await app_manager._input_watcher()

        # Assert
        mock_log_fixture.assert_not_called()


@pytest.mark.asyncio
async def test_periodic_wrapper_stop_during_wait(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test that the periodic wrapper stops during wait."""
    # Arrange
    original_wait = asyncio.wait

    async def wait_side_effect(  # noqa: ASYNC109
        fs: Any,
        timeout: float | None,  # noqa: ASYNC109
        return_when: Any,
    ) -> tuple[set[asyncio.Task[Any]], set[asyncio.Task[Any]]]:  # noqa: ASYNC109
        app_manager._stop_app_event.set()
        done, pending = await original_wait(fs, timeout=timeout, return_when=return_when)
        for task in pending:
            task.cancel()
        return done, pending

    with patch("asyncio.wait", side_effect=wait_side_effect):
        # Act
        await app_manager._periodic_wrapper()

        # Assert
        mock_log_fixture.assert_any_call("⏹️  Остановка — прерываю ожидание.")


@pytest.mark.asyncio
async def test_periodic_wrapper_wait_exception(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test exception during wait in periodic wrapper."""
    # Arrange
    call_count = 0

    async def execute_side_effect(*args: Any, **kwargs: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            app_manager._stop_app_event.set()

    app_manager._execute_task = AsyncMock(side_effect=execute_side_effect)

    with patch("asyncio.wait", side_effect=Exception("Wait error")):
        # Act
        await app_manager._periodic_wrapper()

        # Assert
        mock_log_fixture.assert_any_call("⚠️ Ошибка в ожидании: Wait error")


@pytest.mark.asyncio
async def test_periodic_wrapper_task_exception(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test exception in the periodic task itself."""
    # Arrange
    app_manager._stop_app_event.set()
    app_manager._execute_task = AsyncMock(side_effect=Exception("Task error"))

    # Act
    await app_manager._periodic_wrapper()

    # Assert
    mock_log_fixture.assert_not_called()


@pytest.mark.asyncio
async def test_run_task_group_exception_does_not_log_when_stopping(
    app_manager: AppManager, mock_log_fixture: MagicMock
):
    """Test that exception in task group is not logged when app is stopping."""
    # Arrange
    exception_raised = asyncio.Event()

    async def raise_exception_and_set_event(*args: Any, **kwargs: Any) -> None:
        try:
            raise Exception("Task group error")
        finally:
            exception_raised.set()

    app_manager._input_watcher = AsyncMock(side_effect=raise_exception_and_set_event)

    async def stop_after_exception(*args: Any, **kwargs: Any) -> None:
        await exception_raised.wait()
        app_manager._stop_app_event.set()

    app_manager._periodic_wrapper = AsyncMock(side_effect=stop_after_exception)

    # Act
    await app_manager.run()

    # Assert
    # The log should not be called because the stop event is set
    for call_args in mock_log_fixture.call_args_list:
        assert "Перехвачено исключение в задаче" not in call_args[0][0]
        assert "Возвращаюсь в режим ожидания..." not in call_args[0][0]


def test_setup_signal_handlers_non_windows(app_manager: AppManager) -> None:
    """Test signal handlers setup on non-Windows platforms."""
    # Arrange
    with patch("signal.signal") as mock_signal, patch("sys.platform", "linux"):
        # Act
        app_manager._setup_signal_handlers()

        # Assert
        mock_signal.assert_any_call(signal.SIGTERM, app_manager._shutdown_handler)


@pytest.mark.asyncio
async def test_periodic_wrapper_force_run_clears_event(app_manager: AppManager, mock_task_executor: AsyncMock):
    """Test that the periodic wrapper clears the force run event."""
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
    assert not app_manager._force_run_event.is_set()


@pytest.mark.asyncio
async def test_input_watcher_eof_breaks_loop(app_manager: AppManager):
    """Test that the input watcher loop breaks on EOFError."""
    # Arrange
    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = [EOFError(), "some other input"]

        # Act
        await app_manager._input_watcher()

        # Assert
        mock_ainput.assert_called_once()


@pytest.mark.asyncio
async def test_periodic_wrapper_task_exception_no_stop(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test exception in the periodic task itself when not stopping."""
    # Arrange
    app_manager._execute_task = AsyncMock(side_effect=Exception("Task error"))

    async def stop_loop(*args: Any, **kwargs: Any) -> None:
        app_manager._stop_app_event.set()

    with patch("asyncio.sleep", side_effect=stop_loop) as mock_sleep:
        # Act
        await app_manager._periodic_wrapper()

        # Assert
        mock_log_fixture.assert_any_call("⚠️ Ошибка в периодической задаче: Exception: Task error")
        mock_sleep.assert_awaited_with(1)


@pytest.mark.asyncio
async def test_run_task_group_exception_logs_when_not_stopping(
    app_manager: AppManager, mock_log_fixture: MagicMock, mock_managers: list[AsyncMock]
):
    """Test that exception in task group is logged when app is not stopping."""
    # Arrange
    app_manager._input_watcher = AsyncMock(side_effect=Exception("Task group error"))

    call_count = 0

    async def stop_app_after_a_bit(*args: Any, **kwargs: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            app_manager._stop_app_event.set()

    app_manager._periodic_wrapper = AsyncMock(side_effect=stop_app_after_a_bit)

    # Act
    await app_manager.run()

    # Assert
    mock_log_fixture.assert_any_call("💥 Перехвачено исключение в задаче: Exception: Task group error")
    mock_log_fixture.assert_any_call("🔄 Возвращаюсь в режим ожидания...")
    assert mock_managers[0].update_config.call_count > 1


@pytest.mark.asyncio
async def test_input_watcher_health(app_manager: AppManager):
    """Test the input watcher when 'health' is typed."""
    # Arrange
    app_manager.check_health = AsyncMock()

    with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_ainput:
        mock_ainput.side_effect = ["health", asyncio.CancelledError()]

        # Act
        await app_manager._input_watcher()

        # Assert
        app_manager.check_health.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_health(app_manager: AppManager, mock_log_fixture: MagicMock):
    """Test the check_health method."""
    # Arrange
    health_results = {
        "VK": {"status": "ok"},
        "Telegram": {"status": "error", "message": "Connection failed"},
    }
    app_manager._health_monitor.check_health = AsyncMock(return_value=health_results)

    # Act
    await app_manager.check_health()

    # Assert
    app_manager._health_monitor.check_health.assert_awaited_once()
    mock_log_fixture.assert_any_call("🩺 Результаты проверки состояния:", padding_top=1)
    mock_log_fixture.assert_any_call("  - VK: OK (No message)")
    mock_log_fixture.assert_any_call("  - Telegram: ERROR (Connection failed)")
