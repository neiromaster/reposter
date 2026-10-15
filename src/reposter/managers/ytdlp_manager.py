from __future__ import annotations

import asyncio
import subprocess
import sys
from asyncio import Event
from collections.abc import Callable
from multiprocessing import Process, Queue
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, cast

import psutil
import yt_dlp

from ..config.settings import DownloaderConfig, Settings
from ..interfaces.base_manager import BaseManager
from ..utils.browser import (
    ResolvedFirefoxProfile,
    close_process_tree_gracefully,
    is_firefox_main_process,
    matches_firefox_profile_argv,
    resolve_cookie_profile,
    resolve_firefox_profile,
)
from ..utils.log import log

BROWSER_EXECUTABLES = (
    {
        "firefox": "firefox.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
    }
    if sys.platform == "win32"
    else {
        "firefox": "firefox",
        "chrome": "google-chrome",
        "edge": "microsoft-edge",
    }
)

Result = tuple[Literal["success", "error"], str]


def _ytdlp_worker(url: str, opts: dict[str, Any], out_q: Queue[Result]) -> None:
    """Worker process: downloads a video and sends the result through a queue."""
    try:
        with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            out_q.put(("success", downloaded_file))
    except KeyboardInterrupt:
        pass  # Suppress traceback on Ctrl+C
    except Exception as e:
        out_q.put(("error", str(e)))


def _warn_if_still_running(proc: psutil.Process) -> None:
    """Warns when a browser process survived the graceful close (e.g. elevated Firefox)."""
    try:
        alive = proc.is_running()
    except psutil.Error:
        return
    if alive:
        log(f"⚠️ Процесс {proc.pid} не удалось закрыть — возможно, браузер запущен от администратора.", indent=4)


class YTDLPManager(BaseManager):
    """Handles video downloading via yt-dlp in a separate process."""

    def __init__(self) -> None:
        """Initialize the manager."""
        super().__init__()
        self._initialized = False
        self._active_proc: Process | None = None
        self._downloader_config: DownloaderConfig | None = None

    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event from the AppManager."""
        super().set_shutdown_event(event)

    async def setup(self, settings: Settings) -> None:
        """Prepare the manager for downloading."""
        log("🎥 [YTDLP] Запуск...", indent=1)
        self._downloader_config = settings.downloader
        self._initialized = True
        log("🎥 [YTDLP] Готов к работе.", indent=1)

    async def update_config(self, settings: Settings) -> None:
        """Called when the configuration changes."""
        if not self._initialized:
            await self.setup(settings)
            return
        self._downloader_config = settings.downloader
        log("🎥 [YTDLP] Конфигурация обновлена.", indent=1)

    async def shutdown(self) -> None:
        """Terminate any active download process."""
        if not self._initialized:
            return
        log("🎥 [YTDLP] Завершение работы...", indent=1)
        await self._terminate_active()
        self._initialized = False
        log("🎥 [YTDLP] Остановлен.", indent=1)

    def _build_ydl_opts(self, config: DownloaderConfig) -> dict[str, Any]:
        """Builds yt-dlp options, resolving the cookie source into a cookiesfrombrowser tuple."""
        browser, profile, keyring, container = resolve_cookie_profile(config.cookie_spec)
        return {
            **config.yt_dlp_opts,
            "outtmpl": str(config.output_path / "%(id)s.%(ext)s"),
            "cookiesfrombrowser": (browser, profile, keyring, container),
            "quiet": True,
            "no_warnings": True,
            "verbose": False,
        }

    async def __aenter__(self) -> YTDLPManager:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and shutdown the client."""
        await self.shutdown()

    async def _terminate_active(self) -> None:
        proc = self._active_proc
        if proc and proc.is_alive():
            log("🛑 Прерываю активную загрузку yt-dlp...", indent=4)
            proc.terminate()
            for _ in range(20):
                if not proc.is_alive():
                    break
                await asyncio.sleep(0.1)
            if proc.is_alive():
                proc.kill()
            proc.join(timeout=1.0)
        self._active_proc = None

    async def restart_browser(self) -> None:
        """Restarts the browser — only the target Firefox profile when one is configured."""
        if not self._downloader_config:
            log("⚠️ Конфигурация загрузчика не установлена.", indent=4)
            return

        config = self._downloader_config
        spec = config.cookie_spec
        executable = BROWSER_EXECUTABLES.get(spec.browser)
        if not executable:
            log(f"⚠️ Браузер {spec.browser} не поддерживается для перезапуска.", indent=4)
            return

        resolved: ResolvedFirefoxProfile | None = None
        if spec.browser == "firefox" and spec.profile is not None:
            resolved = resolve_firefox_profile(spec.profile)
            if resolved is None:
                msg = f"⚠️ Профиль Firefox {spec.profile!r} не найден в profiles.ini — перезапускаю весь браузер."
                log(msg, indent=4)

        target = f"{spec.browser} (профиль {resolved.name or resolved.path.name})" if resolved else spec.browser
        log(f"🔄 Перезапускаю {target} для обновления cookie...", indent=4)

        if resolved is not None:
            await self._restart_firefox_profile(config, executable, resolved)
        else:
            await self._restart_whole_browser(config, executable)

        log("✅ Перезапуск завершен.", indent=4)

    async def _collect_browser_processes(
        self, executable: str, predicate: Callable[[list[str]], bool]
    ) -> list[psutil.Process]:
        """Finds browser processes by executable name whose command line satisfies the predicate."""

        def _collect() -> list[psutil.Process]:
            matched: list[psutil.Process] = []
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] != executable:
                    continue
                try:
                    argv = proc.cmdline()
                except psutil.Error:
                    continue
                if predicate(argv):
                    matched.append(proc)
            return matched

        return await asyncio.to_thread(_collect)

    async def _restart_whole_browser(self, config: DownloaderConfig, executable: str) -> None:
        for proc in await self._collect_browser_processes(executable, lambda _argv: True):
            await asyncio.to_thread(close_process_tree_gracefully, proc)
            _warn_if_still_running(proc)

        await asyncio.to_thread(subprocess.Popen, [executable])
        await asyncio.sleep(config.browser_restart_wait_seconds)

        for proc in await self._collect_browser_processes(executable, lambda _argv: True):
            await asyncio.to_thread(close_process_tree_gracefully, proc)
            _warn_if_still_running(proc)

    async def _restart_firefox_profile(
        self, config: DownloaderConfig, executable: str, resolved: ResolvedFirefoxProfile
    ) -> None:
        def _is_target(argv: list[str]) -> bool:
            return is_firefox_main_process(argv) and matches_firefox_profile_argv(argv, resolved)

        exe_path: str | None = None
        for proc in await self._collect_browser_processes(executable, _is_target):
            if exe_path is None:
                try:
                    exe_path = await asyncio.to_thread(proc.exe)
                except (psutil.Error, OSError):
                    exe_path = None
            await asyncio.to_thread(close_process_tree_gracefully, proc)
            _warn_if_still_running(proc)

        launch_args = [exe_path or executable, "--profile", str(resolved.path), "--allow-downgrade"]
        await asyncio.to_thread(subprocess.Popen, launch_args)
        await asyncio.sleep(config.browser_restart_wait_seconds)

        for proc in await self._collect_browser_processes(executable, _is_target):
            await asyncio.to_thread(close_process_tree_gracefully, proc)
            _warn_if_still_running(proc)

    async def download_video(self, video_url: str) -> Path | None:
        """
        Download a video via yt-dlp in a separate process.
        Guaranteed to stop on shutdown or cancellation.
        """
        if not self._downloader_config:
            log("⚠️ Конфигурация загрузчика не установлена. Невозможно скачать видео.", indent=4)
            return None

        self._check_shutdown()

        out_dir = self._downloader_config.output_path
        out_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = self._build_ydl_opts(self._downloader_config)

        retries = self._downloader_config.retries.count
        base_delay = self._downloader_config.retries.delay_seconds

        for attempt in range(retries):
            self._check_shutdown()
            log(f"📥 Скачиваю видео (попытка {attempt + 1}/{retries})...", indent=4)
            out_q: Queue[Result] = Queue()
            proc = Process(target=_ytdlp_worker, args=(video_url, ydl_opts, out_q), daemon=True)
            proc.start()
            self._active_proc = proc

            result = None
            try:
                result = await self._wait_for_result_or_shutdown(proc, out_q)
            except asyncio.CancelledError:
                await self._terminate_active()
                log("⏹️ Загрузка отменена (CancelledError).", indent=4)
                raise

            if result:
                status, payload = result
                if status == "success":
                    log(f"✅ Видео скачано: {payload}", indent=4)
                    return Path(payload)

                # Error handling
                log(f"❌ Ошибка скачивания: {payload}", indent=4)
                error_str = payload.lower()
                if (
                    "доступ ограничен" in error_str
                    or "access restricted" in error_str
                    or "private video" in error_str
                    or "this video is only available for registered users" in error_str
                ) and attempt < retries - 1:
                    log("🔑 Похоже, видео приватное. Пробую перезапустить браузер для обновления cookie...", indent=4)
                    await self.restart_browser()
                    continue

            # Generic retry
            if attempt < retries - 1 and (not self._shutdown_event or not self._shutdown_event.is_set()):
                current_delay = base_delay * (2**attempt)
                log(f"⏳ Пауза {current_delay} секунд перед следующей попыткой...", indent=4)
                await self._sleep_cancelable(current_delay)

        log(f"❌ Не удалось скачать видео после {retries} попыток.", indent=4)
        return None

    async def _wait_for_result_or_shutdown(self, proc: Process, out_q: Queue[Result]) -> Result | None:
        while proc.is_alive():
            if self._shutdown_event and self._shutdown_event.is_set():
                await self._terminate_active()
                raise asyncio.CancelledError()
            try:
                return out_q.get_nowait()
            except Exception:
                pass
            await asyncio.sleep(0.15)

        try:
            return out_q.get_nowait()
        except Exception:
            return None

    async def _sleep_cancelable(self, seconds: int) -> None:
        remaining = float(seconds)
        step = 0.25
        while remaining > 0 and (not self._shutdown_event or not self._shutdown_event.is_set()):
            await asyncio.sleep(step)
            remaining -= step
