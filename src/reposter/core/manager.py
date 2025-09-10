import asyncio
import signal
import sys
from types import FrameType

import aioconsole


class AppManager:
    """
    A cross-platform application manager.
    Supports graceful shutdown on Ctrl+C, starting tasks on Enter,
    and is resilient to exceptions by logging and continuing work.
    Works on Windows and Linux.
    """

    def __init__(self, period: int = 30):
        self._period = period
        self._force_run_event = asyncio.Event()
        self._stop_app_event = asyncio.Event()

    async def _my_task(self):
        """You can place your task's code here."""
        print("Выполняется моя задача...")
        await asyncio.sleep(1)

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
                    print(f"⚠️ Ошибка в input_watcher: {type(e).__name__}: {repr(e)}")

    async def _periodic_wrapper(self):
        """Wraps the periodic task and controls the loop — now supports instant shutdown."""
        while not self._stop_app_event.is_set():
            try:
                await self._my_task()

                print(f"Ожидаю {self._period} секунд (или нажмите Enter для немедленного запуска)...")

                wait_force = asyncio.create_task(self._force_run_event.wait())
                wait_stop = asyncio.create_task(self._stop_app_event.wait())

                try:
                    _, pending = await asyncio.wait(
                        [wait_force, wait_stop],
                        timeout=self._period,
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

            except Exception as e:
                print(f"⚠️ Ошибка в периодической задаче: {e}")
                await asyncio.sleep(1)

    def _shutdown_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handles shutdown signals (synchronous)."""
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._stop_app_event.set)
        print(f"\n🛑 Перехвачен сигнал {signum}, начинаю остановку...")

    def _setup_signal_handlers(self):
        """Sets up signal handlers cross-platform."""
        signal.signal(signal.SIGINT, self._shutdown_handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._shutdown_handler)

    async def run(self):
        """The main entry point that sets up and runs the application."""
        self._setup_signal_handlers()

        print("🚀 Приложение запущено. Нажмите Enter для запуска задачи или Ctrl+C для выхода.")

        while not self._stop_app_event.is_set():
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._input_watcher())
                    tg.create_task(self._periodic_wrapper())
                    await self._stop_app_event.wait()

            except* Exception as eg:
                for exc in eg.exceptions:
                    print(f"💥 Перехвачено исключение в задаче: {type(exc).__name__}: {exc}")
                if not self._stop_app_event.is_set():
                    print("🔄 Возвращаюсь в режим ожидания...")

        print("✅ Приложение остановлено.")
