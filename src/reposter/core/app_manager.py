import asyncio
import signal
import sys
from collections.abc import Sequence
from contextlib import AsyncExitStack
from typing import Any

import aioconsole

from ..interfaces.app_manager import BaseAppManager
from ..interfaces.base_manager import BaseManager
from ..interfaces.task_executor import BaseTaskExecutor
from ..managers.boosty_manager import BoostyManager
from ..managers.telegram_manager import TelegramManager
from ..managers.vk_manager import VKManager
from ..utils.log import log
from .health_monitor import HealthMonitor
from .settings_manager import SettingsManager


class AppManager(BaseAppManager):
    def __init__(
        self,
        managers: Sequence[BaseManager],
        task_executor: BaseTaskExecutor,
    ) -> None:
        self._managers = managers
        self._task_executor = task_executor
        self._force_run_event = asyncio.Event()
        self._stop_app_event = asyncio.Event()
        self._settings_manager = SettingsManager()
        self._health_monitor = HealthMonitor()

    async def _execute_task(self) -> None:
        """Wrapper for executing a task - contains no business logic."""
        try:
            settings = self._settings_manager.get_settings()
            await self._task_executor.execute(settings)
            if not self._stop_app_event.is_set():
                log("✅ Задача успешно завершена.")
        except asyncio.CancelledError:
            log("⏹️ Задача прервана.")
        except Exception as e:
            if not self._stop_app_event.is_set():
                log(f"❌ Ошибка в задаче: {type(e).__name__}: {e}")

    async def _input_watcher(self) -> None:
        """Asynchronously waits for user input and sets events."""
        while not self._stop_app_event.is_set():
            try:
                command = await aioconsole.ainput()
                if self._stop_app_event.is_set():
                    break

                if command.strip().lower() == "health":
                    log("🩺 Запрос проверки состояния...", padding_top=1)
                    await self.check_health()
                else:
                    log("⌨️ Enter нажат, запускаю задачу вне очереди...", padding_top=1)
                    self._force_run_event.set()

            except (asyncio.CancelledError, EOFError):
                break
            except Exception as e:
                if not self._stop_app_event.is_set():
                    log(f"⚠️ Ошибка в input_watcher: {type(e).__name__}: {e}")

    async def _periodic_wrapper(self) -> None:
        """Wraps the periodic task and controls the loop — now supports instant shutdown."""
        while not self._stop_app_event.is_set():
            try:
                await self._execute_task()

                if self._stop_app_event.is_set():
                    break

                try:
                    settings = self._settings_manager.get_settings()
                    timeout = settings.app.wait_time_seconds

                    wait_force = asyncio.create_task(self._force_run_event.wait())
                    wait_stop = asyncio.create_task(self._stop_app_event.wait())

                    log(f"⏳ Ожидаю {timeout} сек... Enter - запуск, 'health' - проверка.", padding_top=1)
                    try:
                        _, pending = await asyncio.wait(
                            [wait_force, wait_stop],
                            timeout=timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        for task in pending:
                            task.cancel()

                        if self._stop_app_event.is_set():
                            log("⏹️  Остановка — прерываю ожидание.")
                            break

                        if self._force_run_event.is_set():
                            self._force_run_event.clear()

                    except Exception as e:
                        log(f"⚠️ Ошибка в ожидании: {e}")
                except TimeoutError:
                    pass

                if self._force_run_event.is_set():
                    self._force_run_event.clear()

            except Exception as e:
                if not self._stop_app_event.is_set():
                    log(f"⚠️ Ошибка в периодической задаче: {type(e).__name__}: {e}")
                await asyncio.sleep(1)

    def _shutdown_handler(self, signum: int, frame: Any) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._stop_app_event.set)
        log(f"🛑 Перехвачен сигнал {signum}, начинаю остановку...", padding_top=1)

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._shutdown_handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._shutdown_handler)

    async def check_health(self) -> None:
        """Runs health checks for all registered managers."""
        results = await self._health_monitor.check_health()
        log("🩺 Результаты проверки состояния:", padding_top=1)
        for name, result in results.items():
            status = result.get("status", "error")
            message = result.get("message", "No message")
            log(f"  - {name}: {status.upper()} ({message})")

    async def run(self) -> None:
        """Main loop - manages the lifecycle, but not the business logic."""
        settings = self._settings_manager.get_settings()

        self._setup_signal_handlers()
        log("🚀 Приложение запущено. Enter - запуск, 'health' - проверка, Ctrl+C - выход.")

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
                            tg.create_task(self._periodic_wrapper())
                            await self._stop_app_event.wait()
                    except* Exception as eg:
                        for exc in eg.exceptions:
                            if not self._stop_app_event.is_set():
                                log(f"💥 Перехвачено исключение в задаче: {type(exc).__name__}: {exc}")
                        if not self._stop_app_event.is_set():
                            log("🔄 Возвращаюсь в режим ожидания...")
            finally:
                log("🔌 Завершение работы...")

        log("✅ Приложение остановлено.")
