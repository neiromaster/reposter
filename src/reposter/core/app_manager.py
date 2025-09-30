import asyncio
import signal
import sys
from collections.abc import Sequence
from contextlib import AsyncExitStack, suppress
from typing import Any

import aioconsole

from ..interfaces.app_manager import BaseAppManager
from ..interfaces.base_manager import BaseManager
from ..interfaces.task_executor import BaseTaskExecutor
from ..managers.boosty_manager import BoostyManager
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_manager import VKManager
from ..utils.log import log
from .event_system import (
    AppStartEvent,
    AppStopEvent,
    Event,
    EventManager,
    HealthCheckRequestEvent,
    TaskExecutionCompleteEvent,
    TaskExecutionRequestEvent,
    UserInputReceivedEvent,
)
from .health_monitor import HealthMonitor
from .settings_manager import SettingsManager


class AppManager(BaseAppManager):
    def __init__(
        self,
        managers: Sequence[BaseManager],
        task_executor: BaseTaskExecutor,
        event_manager: EventManager,
    ) -> None:
        self._managers = managers
        self._task_executor = task_executor
        self._event_manager = event_manager
        self._stop_app_event = asyncio.Event()
        self._settings_manager = SettingsManager()
        self._health_monitor = HealthMonitor()
        self._event_handlers_registered = False

    async def _handle_task_execution_request(self, event: Event) -> None:
        """Handle task execution request event."""
        try:
            settings = self._settings_manager.get_settings()
            await self._task_executor.execute(settings)
            if not self._stop_app_event.is_set():
                log("✅ Задача успешно завершена.")
                await self._event_manager.emit(TaskExecutionCompleteEvent(success=True))
        except asyncio.CancelledError:
            log("⏹️ Задача прервана.")
            await self._event_manager.emit(TaskExecutionCompleteEvent(success=False, error="Cancelled"))
        except Exception as e:
            if not self._stop_app_event.is_set():
                log(f"❌ Ошибка в задаче: {type(e).__name__}: {e}")
                await self._event_manager.emit(TaskExecutionCompleteEvent(success=False, error=str(e)))

    async def _handle_user_input(self, event: Event) -> None:
        """Handle user input event."""
        command = event.data.get("command", "")

        if command.strip().lower() == "health":
            log("🩺 Запрос проверки состояния...", padding_top=1)
            await self._event_manager.emit(HealthCheckRequestEvent())
        else:
            log("⌨️ Enter нажат, запускаю задачу вне очереди...", padding_top=1)
            await self._event_manager.emit(TaskExecutionRequestEvent(force=True))

    async def _handle_health_check_request(self, event: Event) -> None:
        """Handle health check request event."""
        results = await self._health_monitor.check_health()
        log("🩺 Результаты проверки состояния:", padding_top=1)
        for name, result in results.items():
            status = result.get("status", "error")
            message = result.get("message", "No message")
            log(f"  - {name}: {status.upper()} ({message})")

    async def _input_watcher(self) -> None:
        """Asynchronously waits for user input and emits events."""
        while not self._stop_app_event.is_set():
            try:
                command = await aioconsole.ainput()
                if self._stop_app_event.is_set():
                    break

                await self._event_manager.emit(UserInputReceivedEvent(command))
            except (asyncio.CancelledError, EOFError):
                break
            except Exception as e:
                if not self._stop_app_event.is_set():
                    log(f"⚠️ Ошибка в input_watcher: {type(e).__name__}: {e}")

    async def _periodic_task_scheduler(self) -> None:
        """Schedule periodic tasks based on settings."""
        while not self._stop_app_event.is_set():
            try:
                # Execute task immediately on startup
                await self._event_manager.emit(TaskExecutionRequestEvent())

                if self._stop_app_event.is_set():
                    break

                try:
                    settings = self._settings_manager.get_settings()
                    timeout = settings.app.wait_time_seconds

                    log(f"⏳ Ожидаю {timeout} сек... Enter - запуск, 'health' - проверка.", padding_top=1)

                    # Wait for either stop event or timeout
                    wait_stop = asyncio.create_task(self._stop_app_event.wait())
                    delay_task = asyncio.create_task(asyncio.sleep(timeout))

                    _, pending = await asyncio.wait([wait_stop, delay_task], return_when=asyncio.FIRST_COMPLETED)

                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task

                    if self._stop_app_event.is_set():
                        log("⏹️  Остановка — прерываю ожидание.")
                        break

                except TimeoutError:
                    pass

            except Exception as e:
                if not self._stop_app_event.is_set():
                    log(f"⚠️ Ошибка в планировщике периодических задач: {type(e).__name__}: {e}")
                await asyncio.sleep(1)

    def _shutdown_handler(self, signum: int, frame: Any) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._stop_app_event.set)
        log(f"🛑 Перехвачен сигнал {signum}, начинаю остановку...", padding_top=1)

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._shutdown_handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _register_event_handlers(self) -> None:
        """Register event handlers for various events."""
        if self._event_handlers_registered:
            return

        self._event_manager.subscribe("TASK_EXECUTION_REQUEST", self._handle_task_execution_request)
        self._event_manager.subscribe("USER_INPUT_RECEIVED", self._handle_user_input)
        self._event_manager.subscribe("HEALTH_CHECK_REQUEST", self._handle_health_check_request)
        self._event_handlers_registered = True

    async def run(self) -> None:
        """Main loop - manages the lifecycle, but not the business logic."""
        settings = self._settings_manager.get_settings()

        # Register event handlers
        self._register_event_handlers()

        self._setup_signal_handlers()
        log("🚀 Приложение запущено. Enter - запуск, 'health' - проверка, Ctrl+C - выход.")

        # Emit app start event
        await self._event_manager.emit(AppStartEvent())

        self._task_executor.set_shutdown_event(self._stop_app_event)

        async with AsyncExitStack() as stack:
            log("🔌 Запуск менеджеров...")
            for manager in self._managers:
                manager.set_shutdown_event(self._stop_app_event)
                await manager.setup(settings)
                await stack.enter_async_context(manager)

                if isinstance(manager, VKManager):
                    self._health_monitor.register_check("VK", manager.health_check)
                elif isinstance(manager, TelegramManager):
                    self._health_monitor.register_check("Telegram", manager.health_check)
                elif isinstance(manager, BoostyManager):
                    self._health_monitor.register_check("Boosty", manager.health_check)
            log("✅ Менеджеры инициализированы.")

            try:
                while not self._stop_app_event.is_set():
                    settings = self._settings_manager.get_settings()
                    for manager in self._managers:
                        await manager.update_config(settings)

                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(self._input_watcher())
                            tg.create_task(self._periodic_task_scheduler())
                            await self._stop_app_event.wait()
                    except* Exception as eg:
                        for exc in eg.exceptions:
                            if not self._stop_app_event.is_set():
                                log(f"💥 Перехвачено исключение в задаче: {type(exc).__name__}: {exc}")
                        if not self._stop_app_event.is_set():
                            log("🔄 Возвращаюсь в режим ожидания...")
            finally:
                log("🔌 Завершение работы...")
                # Emit app stop event
                await self._event_manager.emit(AppStopEvent())

        log("✅ Приложение остановлено.")
