"""Fetches Firefox cookies from a remote Windows machine over SSH.

Copies profiles.ini and cookies.sqlite (+ -wal/-shm) from the remote Firefox
directory via the system scp, parses the cookie database locally with stdlib
sqlite3 and writes a Netscape cookies.txt consumable by yt-dlp's `cookiefile`.
Cookie refresh opens a vk.com tab in the remote Firefox via `cmd /c start`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Final

from ..config.settings import CookiesViaSshConfig

CONNECT_TIMEOUT_SECONDS: Final[int] = 15
COMMAND_TIMEOUT_SECONDS: Final[float] = 15.0
VK_REFRESH_URL: Final[str] = "https://vk.com"
_REMOTE_FIREFOX_DIR: Final[str] = "AppData/Roaming/Mozilla/Firefox"
_CACHE_FILE_NAME: Final[str] = "reposter-ssh-cookies.txt"


class CookieFetchError(RuntimeError):
    """Raised when cookies cannot be fetched from the remote machine."""


def cookies_cache_path() -> Path:
    """Stable cache path: yt-dlp workers re-read the file at every start."""
    return Path(tempfile.gettempdir()) / _CACHE_FILE_NAME


def _ssh_common_args(cfg: CookiesViaSshConfig) -> list[str]:
    args = [
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if cfg.keyfile:
        args += ["-i", str(cfg.keyfile)]
    args += list(cfg.extra_ssh_args)
    return args


def _build_ssh_command(  # type: ignore[reportUnusedFunction]
    cfg: CookiesViaSshConfig, remote_command: str
) -> list[str]:
    return ["ssh", "-p", str(cfg.port), *_ssh_common_args(cfg), f"{cfg.user}@{cfg.host}", remote_command]


def _build_scp_command(  # type: ignore[reportUnusedFunction]
    cfg: CookiesViaSshConfig, remote_path: str, local_path: Path
) -> list[str]:
    # scp spells the port option with a capital -P (lowercase -p preserves mtimes).
    return [
        "scp",
        "-P",
        str(cfg.port),
        *_ssh_common_args(cfg),
        f"{cfg.user}@{cfg.host}:{remote_path}",
        str(local_path),
    ]


def _build_open_tab_command(cfg: CookiesViaSshConfig) -> str:  # type: ignore[reportUnusedFunction]
    firefox = cfg.firefox_path or "firefox.exe"
    # `start` detaches the process so ssh returns immediately; -headless keeps a
    # fresh instance working in a headless SSH session (harmless when Firefox is
    # already running — the running instance just gets the URL).
    return f'cmd /c start "" "{firefox}" -headless -P "{cfg.profile}" {VK_REFRESH_URL}'
