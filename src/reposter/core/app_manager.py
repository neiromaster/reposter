import asyncio
import signal
import sys
from collections.abc import Sequence
from typing import Any

import aioconsole

from ..interfaces.base_manager import BaseManager
from ..interfaces.task_executor import BaseTaskExecutor
from .settings_manager import SettingsManager


class AppManager:
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

    async def _execute_task(self) -> None:
        """Wrapper for executing a task - contains no business logic."""
        try:
            settings = self._settings_manager.get_settings()
            await self._task_executor.execute(settings)
            print("✅ Задача успешно завершена.")
        except Exception as e:
            print(f"❌ Ошибка в задаче: {type(e).__name__}: {e}")

    async def _input_watcher(self) -> None:
        """Asynchronously waits for the Enter key and sets the force_run_event."""
        while not self._stop_app_event.is_set():
            try:
                await aioconsole.ainput()
                if not self._stop_app_event.is_set():
                    print("\nEnter нажат, запускаю задачу вне очереди...")
                    self._force_run_event.set()
            except (asyncio.CancelledError, EOFError):
                break
            except Exception as e:
                if not self._stop_app_event.is_set():
                    print(f"⚠️ Ошибка в input_watcher: {type(e).__name__}: {e}")

    async def _periodic_wrapper(self) -> None:
        """Wraps the periodic task and controls the loop — now supports instant shutdown."""
        while not self._stop_app_event.is_set():
            try:
                await self._execute_task()
                try:
                    settings = self._settings_manager.get_settings()
                    timeout = settings.app.wait_time_seconds

                    wait_force = asyncio.create_task(self._force_run_event.wait())
                    wait_stop = asyncio.create_task(self._stop_app_event.wait())

                    print(f"Ожидаю {timeout} сек...")
                    try:
                        _, pending = await asyncio.wait(
                            [wait_force, wait_stop],
                            timeout=timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        for task in pending:
                            task.cancel()

                        if self._stop_app_event.is_set():
                            print("⏹️  Остановка — прерываю ожидание.")
                            break

                        if self._force_run_event.is_set():
                            self._force_run_event.clear()

                    except Exception as e:
                        print(f"⚠️ Ошибка в ожидании: {e}")
                except TimeoutError:
                    pass

                if self._force_run_event.is_set():
                    self._force_run_event.clear()

            except Exception as e:
                if not self._stop_app_event.is_set():
                    print(f"⚠️ Ошибка в периодической задаче: {type(e).__name__}: {e}")
                await asyncio.sleep(1)

    def _shutdown_handler(self, signum: int, frame: Any) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._stop_app_event.set)
        print(f"\n🛑 Перехвачен сигнал {signum}, начинаю остановку...")

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._shutdown_handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._shutdown_handler)

    async def run(self) -> None:
        """Main loop - manages the lifecycle, but not the business logic."""
        settings = self._settings_manager.get_settings()

        print("🔌 Инициализация менеджеров...")
        for manager in self._managers:
            await manager.setup(settings)

        self._setup_signal_handlers()
        print("🚀 Приложение запущено. Нажмите Enter для запуска задачи или Ctrl+C для выхода.")

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
                            print(f"💥 Перехвачено исключение в задаче: {type(exc).__name__}: {exc}")
                    if not self._stop_app_event.is_set():
                        print("🔄 Возвращаюсь в режим ожидания...")
        finally:
            print("🔌 Завершение работы менеджеров...")
            for manager in self._managers:
                await manager.shutdown()
            print("✅ Приложение остановлено.")
