import asyncio
import signal
import sys
from contextlib import suppress

import aioconsole

force_run_event = asyncio.Event()
stop_app_event = asyncio.Event()


async def input_watcher():
    """Asynchronously waits for the Enter key and sets the force_run_event."""
    while not stop_app_event.is_set():
        try:
            await aioconsole.ainput()
            if not stop_app_event.is_set():
                print("\nEnter нажат, запускаю задачу вне очереди...")
                force_run_event.set()
        except asyncio.CancelledError:
            break


async def my_task():
    """You can place your task's code here."""
    print("Выполняется моя задача...")
    await asyncio.sleep(1)


async def periodic_wrapper(period: int):
    """Wraps the periodic task and controls the loop."""
    while not stop_app_event.is_set():
        await my_task()
        try:
            print(f"Ожидаю {period} секунд (или нажмите Enter для немедленного запуска)...")
            await asyncio.wait_for(force_run_event.wait(), timeout=period)
        except TimeoutError:
            pass

        if force_run_event.is_set():
            force_run_event.clear()


async def main():
    """The main asynchronous function that sets up all components."""
    loop = asyncio.get_running_loop()

    def shutdown_handler():
        if not stop_app_event.is_set():
            print("\nПерехвачен сигнал, начинаю остановку...")
            stop_app_event.set()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_handler)

    print("Приложение запущено. Нажмите Enter для запуска задачи или Ctrl+C для выхода.")
    input_task = asyncio.create_task(input_watcher())

    period = 10
    main_task = asyncio.create_task(periodic_wrapper(period))

    tasks = [input_task, main_task]

    try:
        await stop_app_event.wait()
    except asyncio.CancelledError:
        stop_app_event.set()

    print("Остановка...")
    for task in tasks:
        if not task.done():
            task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    print("Приложение остановлено.")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
