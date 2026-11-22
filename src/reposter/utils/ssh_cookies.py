"""Fetches Firefox cookies from a remote Windows machine over SSH.

Copies profiles.ini and cookies.sqlite (+ -wal/-shm) from the remote Firefox
directory via the system scp, parses the cookie database locally with stdlib
sqlite3 and writes a Netscape cookies.txt consumable by yt-dlp's `cookiefile`.
Cookie refresh opens a vk.com tab in the remote Firefox via `cmd /c start`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import sqlite3
import tempfile
import time
from asyncio import create_subprocess_exec
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..config.settings import CookiesViaSshConfig
from .browser import resolve_firefox_profile

CONNECT_TIMEOUT_SECONDS: Final[int] = 15
# Command budget must exceed ConnectTimeout (15) so ssh's own "Connection timed out"
# wins the race and lands in the CookieFetchError message instead of a bare TimeoutError.
COMMAND_TIMEOUT_SECONDS: Final[float] = 20.0
VK_REFRESH_URL: Final[str] = "https://vk.com"
_REMOTE_FIREFOX_DIR: Final[str] = "AppData/Roaming/Mozilla/Firefox"
_CACHE_FILE_NAME: Final[str] = "reposter-ssh-cookies.txt"


class CookieFetchError(RuntimeError):
    """Raised when cookies cannot be fetched from the remote machine."""


@dataclass(frozen=True)
class CookieRow:
    """A single cookie row parsed from the copied cookies.sqlite."""

    host: str
    path: str
    secure: bool
    http_only: bool
    expiry: int
    name: str
    value: str


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


def _build_ssh_command(cfg: CookiesViaSshConfig, remote_command: str) -> list[str]:
    return ["ssh", "-p", str(cfg.port), *_ssh_common_args(cfg), f"{cfg.user}@{cfg.host}", remote_command]


def _build_scp_command(cfg: CookiesViaSshConfig, remote_path: str, local_path: Path) -> list[str]:
    # scp spells the port option with a capital -P (lowercase -p preserves mtimes).
    return [
        "scp",
        "-P",
        str(cfg.port),
        *_ssh_common_args(cfg),
        f"{cfg.user}@{cfg.host}:{remote_path}",
        str(local_path),
    ]


def _build_open_tab_command(cfg: CookiesViaSshConfig) -> str:
    firefox = cfg.firefox_path or "firefox.exe"
    # `start` detaches the process so ssh returns immediately; -headless keeps a
    # fresh instance working in a headless SSH session (harmless when Firefox is
    # already running — the running instance just gets the URL).
    return f'cmd /c start "" "{firefox}" -headless -P "{cfg.profile}" {VK_REFRESH_URL}'


async def _run_command(args: list[str]) -> str:
    """Runs an ssh/scp command; returns stdout, raises CookieFetchError on failure."""
    # Bare bound name (not asyncio.create_subprocess_exec) so tests can patch the module attribute.
    proc = await create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=COMMAND_TIMEOUT_SECONDS)
    except BaseException as exc:
        # Never leak a hung child: kill it and reap it before propagating
        # (TimeoutError, CancelledError or anything else) to the caller.
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(BaseException):
            await proc.wait()
        if isinstance(exc, TimeoutError):
            # A bare TimeoutError stringifies to "" — wrap it so the manager's
            # failure log stays diagnosable and optional scp calls can suppress it.
            raise CookieFetchError(f"{args[0]} превысил таймаут {COMMAND_TIMEOUT_SECONDS} с") from exc
        raise
    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace").strip()
        raise CookieFetchError(f"{args[0]} завершился с кодом {proc.returncode}: {stderr_text}")
    return stdout.decode(errors="replace")


def _remote_cookie_db_paths(profile_dir: Path, ini_dir: Path) -> str:
    """Composes the remote cookies.sqlite path from the profile resolved via the copied profiles.ini."""
    try:
        relative = profile_dir.relative_to(ini_dir)
    except ValueError:
        # profiles.ini stored an absolute path — it is valid as-is on the remote host.
        return f"{profile_dir.as_posix()}/cookies.sqlite"
    return f"{_REMOTE_FIREFOX_DIR}/{relative.as_posix()}/cookies.sqlite"


def _read_cookie_rows(db_path: Path, *, now: int | None = None) -> list[CookieRow]:
    """Reads unexpired cookies from the copied cookies.sqlite."""
    current = int(time.time()) if now is None else now
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT host, path, isSecure, isHttpOnly, expiry, name, value FROM moz_cookies WHERE expiry > ?",
            (current,),
        ).fetchall()
    except sqlite3.Error as e:
        raise CookieFetchError(f"Не удалось прочитать cookies.sqlite: {e}") from e
    finally:
        connection.close()
    return [
        CookieRow(host=r[0], path=r[1], secure=bool(r[2]), http_only=bool(r[3]), expiry=r[4], name=r[5], value=r[6])
        for r in rows
    ]


def _write_netscape_file(cache_path: Path, rows: list[CookieRow]) -> None:
    """Writes rows in Netscape cookies.txt format, atomically (tmp + os.replace)."""
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated by reposter from a remote Firefox cookies.sqlite.",
    ]
    for row in rows:
        # Firefox stores domain cookies with a leading dot in `host`. The flag
        # column follows the curl convention (dot -> TRUE, host-only -> FALSE);
        # yt-dlp keys on the leading dot, the flag keeps the file portable.
        flag = "TRUE" if row.host.startswith(".") else "FALSE"
        prefix = "#HttpOnly_" if row.http_only else ""
        secure = "TRUE" if row.secure else "FALSE"
        lines.append(f"{prefix}{row.host}\t{flag}\t{row.path}\t{secure}\t{row.expiry}\t{row.name}\t{row.value}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_name(cache_path.name + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # The cache holds a live VK session: restrict it to the owner before it lands
    # on the final (possibly world-readable, e.g. /tmp) location. os.replace
    # keeps the source file's mode, so there is never an exposed final file.
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, cache_path)


async def fetch_cookies_via_ssh(cfg: CookiesViaSshConfig, cache_path: Path) -> Path:
    """Fetches Firefox cookies from the remote machine into a Netscape cookies.txt."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="reposter-ssh-cookies-"))
    try:
        ini_local = tmp_dir / "profiles.ini"
        await _run_command(_build_scp_command(cfg, f"{_REMOTE_FIREFOX_DIR}/profiles.ini", ini_local))
        resolved = resolve_firefox_profile(cfg.profile, ini_path=ini_local)
        if resolved is None:
            raise CookieFetchError(f"Профиль Firefox {cfg.profile!r} не найден в profiles.ini на {cfg.host}")

        remote_db = _remote_cookie_db_paths(resolved.path, ini_local.parent)
        db_local = tmp_dir / "cookies.sqlite"
        await _run_command(_build_scp_command(cfg, remote_db, db_local))
        for suffix in ("-wal", "-shm"):
            # Both are absent when Firefox is closed; a failed side-copy never fails the fetch.
            with contextlib.suppress(CookieFetchError):
                await _run_command(_build_scp_command(cfg, f"{remote_db}{suffix}", tmp_dir / f"cookies.sqlite{suffix}"))

        rows = _read_cookie_rows(db_local)
        if not rows:
            msg = f"В cookies.sqlite на {cfg.host} нет действующих кук — выполните вход в VK на удалённой машине"
            raise CookieFetchError(msg)
        _write_netscape_file(cache_path, rows)
        return cache_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def refresh_cookies_via_ssh(cfg: CookiesViaSshConfig, cache_path: Path, *, wait_seconds: int) -> Path:
    """Refreshes cookies: opens vk.com in the remote Firefox, waits, re-fetches."""
    await _run_command(_build_ssh_command(cfg, _build_open_tab_command(cfg)))
    await asyncio.sleep(wait_seconds)
    return await fetch_cookies_via_ssh(cfg, cache_path)
