# pyright: reportPrivateUsage=false
import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.config.settings import CookiesViaSshConfig
from src.reposter.utils.ssh_cookies import (
    CookieFetchError,
    CookieRow,
    _build_open_tab_command,
    _build_scp_command,
    _build_ssh_command,
    _read_cookie_rows,
    _remote_cookie_db_paths,
    _run_command,
    _write_netscape_file,
    cookies_cache_path,
    fetch_cookies_via_ssh,
    refresh_cookies_via_ssh,
)


def _ssh_cfg(**overrides: Any) -> CookiesViaSshConfig:
    defaults: dict[str, Any] = {
        "enabled": True,
        "host": "192.0.2.10",
        "port": 22,
        "user": "vasya",
        "profile": "default-release",
    }
    return CookiesViaSshConfig(**{**defaults, **overrides})


def test_cookies_cache_path_filename():
    path = cookies_cache_path()
    assert path.name == "reposter-ssh-cookies.txt"
    assert path.parent == Path(tempfile.gettempdir())


def test_build_ssh_command_defaults():
    command = _build_ssh_command(_ssh_cfg(), "remote cmd")
    assert command == [
        "ssh",
        "-p",
        "22",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "vasya@192.0.2.10",
        "remote cmd",
    ]


def test_build_ssh_command_keyfile_and_extra_args():
    cfg = _ssh_cfg(keyfile="C:/keys/id_ed25519", extra_ssh_args=["-J", "jump@host"])
    command = _build_ssh_command(cfg, "remote cmd")
    assert command == [
        "ssh",
        "-p",
        "22",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        "C:/keys/id_ed25519",
        "-J",
        "jump@host",
        "vasya@192.0.2.10",
        "remote cmd",
    ]


def test_build_scp_command_uses_capital_p():
    command = _build_scp_command(_ssh_cfg(), "AppData/Roaming/Mozilla/Firefox/profiles.ini", Path("local.ini"))
    assert command[0] == "scp"
    assert command[1:3] == ["-P", "22"]
    assert "BatchMode=yes" in command
    assert command[-2] == "vasya@192.0.2.10:AppData/Roaming/Mozilla/Firefox/profiles.ini"
    assert command[-1] == str(Path("local.ini"))


def test_build_open_tab_command_default_firefox():
    command = _build_open_tab_command(_ssh_cfg())
    assert command == 'cmd /c start "" "firefox.exe" -headless -P "default-release" https://vk.com'


def test_build_open_tab_command_explicit_path_quoted():
    cfg = _ssh_cfg(firefox_path="C:/Program Files/Mozilla Firefox/firefox.exe")
    command = _build_open_tab_command(cfg)
    assert (
        command
        == 'cmd /c start "" "C:/Program Files/Mozilla Firefox/firefox.exe" -headless -P "default-release" https://vk.com'
    )


def test_build_scp_command_full_argv_with_keyfile_and_extra_args():
    cfg = _ssh_cfg(keyfile="C:/keys/id_ed25519", port=2202, extra_ssh_args=["-vv"])
    command = _build_scp_command(cfg, "AppData/Roaming/Mozilla/Firefox/profiles.ini", Path("local.ini"))
    assert command == [
        "scp",
        "-P",
        "2202",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        "C:/keys/id_ed25519",
        "-vv",
        "vasya@192.0.2.10:AppData/Roaming/Mozilla/Firefox/profiles.ini",
        "local.ini",
    ]


INI_TEXT = """[Install4F96C1931A91105F]
Default=Profiles/abc123.default-release

[Profile1]
Name=default-release
IsRelative=1
Path=Profiles/abc123.default-release
Default=1
"""


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    """Builds a fake asyncio subprocess with a completed communicate()."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    proc.returncode = returncode
    return proc


async def _communicate_hang() -> tuple[bytes, bytes]:
    await asyncio.sleep(10)
    raise AssertionError("communicate should have been cancelled")


async def _communicate_hang_signal(started: asyncio.Event) -> tuple[bytes, bytes]:
    started.set()
    await asyncio.sleep(10)
    raise AssertionError("communicate should have been cancelled")


def _cookie_db_bytes(tmp_path: Path, rows: list[tuple[str, str, str, str, int, int, int]] | None = None) -> bytes:
    db = tmp_path / "source-cookies.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE moz_cookies "
        "(name TEXT, value TEXT, host TEXT, path TEXT, expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER)"
    )
    if rows is None:
        rows = [
            ("auth", "v1", "vk.com", "/", 4102444800, 1, 1),  # host-only, secure, httpOnly
            ("lid", "l", ".vk.com", "/", 4102444800, 0, 0),  # domain cookie
            ("old", "gone", "vk.com", "/", 1000000000, 0, 0),  # expired
        ]
    con.executemany("INSERT INTO moz_cookies VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return db.read_bytes()


def _fake_run(files: dict[str, bytes | Exception]) -> tuple[Any, list[list[str]]]:
    """Returns (async _run_command stub, captured command lists). The stub
    materializes the "copied" file locally, like scp would."""
    captured: list[list[str]] = []

    async def fake(args: list[str]) -> str:
        captured.append(args)
        payload = files.get(Path(args[-1]).name)
        if isinstance(payload, Exception):
            raise payload
        if payload is not None:
            Path(args[-1]).write_bytes(payload)
        return ""

    return fake, captured


@pytest.mark.asyncio
async def test_run_command_returns_stdout():
    with patch("src.reposter.utils.ssh_cookies.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_proc(returncode=0, stdout=b"hello")
        assert await _run_command(["ssh", "x"]) == "hello"


@pytest.mark.asyncio
async def test_run_command_nonzero_raises_with_stderr():
    with patch("src.reposter.utils.ssh_cookies.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_proc(returncode=1, stderr=b"boom")
        with pytest.raises(CookieFetchError) as exc_info:
            await _run_command(["scp", "x"])
    assert "1" in str(exc_info.value) and "boom" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_command_timeout_kills_process():
    proc = _make_proc()
    proc.communicate = AsyncMock(side_effect=_communicate_hang)
    with (
        patch("src.reposter.utils.ssh_cookies.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
        patch("src.reposter.utils.ssh_cookies.COMMAND_TIMEOUT_SECONDS", 0.05),
    ):
        mock_exec.return_value = proc
        with pytest.raises(CookieFetchError, match="превысил таймаут"):
            await _run_command(["ssh", "x"])
    assert proc.kill.called
    proc.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_command_cancel_kills_child_and_propagates():
    started = asyncio.Event()
    proc = _make_proc()

    # side_effect must be a coroutine function: AsyncMock awaits those, but a
    # plain lambda's returned coroutine would come back un-awaited as a value.
    async def _signal_then_hang() -> tuple[bytes, bytes]:
        return await _communicate_hang_signal(started)

    proc.communicate = AsyncMock(side_effect=_signal_then_hang)
    with patch("src.reposter.utils.ssh_cookies.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc
        task = asyncio.create_task(_run_command(["ssh", "x"]))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert proc.kill.called
    proc.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_happy_path_writes_netscape_file(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    fake, captured = _fake_run({"profiles.ini": INI_TEXT.encode(), "cookies.sqlite": _cookie_db_bytes(tmp_path)})
    with patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake):
        result = await fetch_cookies_via_ssh(_ssh_cfg(), cache)
    assert result == cache
    content = cache.read_text(encoding="utf-8")
    assert "#HttpOnly_vk.com\tFALSE\t/\tTRUE\t4102444800\tauth\tv1" in content
    assert ".vk.com\tTRUE\t/\tFALSE\t4102444800\tlid\tl" in content
    assert "old" not in content
    assert not list(tmp_path.glob("*.tmp"))
    remote_paths = [" ".join(args) for args in captured]
    assert any(
        "vasya@192.0.2.10:AppData/Roaming/Mozilla/Firefox/Profiles/abc123.default-release/cookies.sqlite" in p
        for p in remote_paths
    )
    assert any("vasya@192.0.2.10:AppData/Roaming/Mozilla/Firefox/profiles.ini" in p for p in remote_paths)


@pytest.mark.asyncio
async def test_fetch_tolerates_missing_wal_and_shm(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    fake, _captured = _fake_run(
        {
            "profiles.ini": INI_TEXT.encode(),
            "cookies.sqlite": _cookie_db_bytes(tmp_path),
            "cookies.sqlite-wal": CookieFetchError("scp: cookies.sqlite-wal: No such file"),
            "cookies.sqlite-shm": CookieFetchError("scp: cookies.sqlite-shm: No such file"),
        }
    )
    with patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake):
        result = await fetch_cookies_via_ssh(_ssh_cfg(), cache)
    assert result == cache


@pytest.mark.asyncio
async def test_fetch_ini_missing_leaves_cache_untouched(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    cache.write_text("OLD", encoding="utf-8")
    fake, _captured = _fake_run({"profiles.ini": CookieFetchError("scp: profiles.ini: No such file")})
    with patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake), pytest.raises(CookieFetchError):
        await fetch_cookies_via_ssh(_ssh_cfg(), cache)
    assert cache.read_text(encoding="utf-8") == "OLD"


@pytest.mark.asyncio
async def test_fetch_unknown_profile_raises(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    ini = INI_TEXT.replace("default-release", "other-profile")
    fake, _captured = _fake_run({"profiles.ini": ini.encode(), "cookies.sqlite": _cookie_db_bytes(tmp_path)})
    with (
        patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake),
        pytest.raises(CookieFetchError) as exc_info,
    ):
        await fetch_cookies_via_ssh(_ssh_cfg(), cache)
    assert "не найден" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_empty_cookie_db_raises(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    fake, _captured = _fake_run(
        {"profiles.ini": INI_TEXT.encode(), "cookies.sqlite": _cookie_db_bytes(tmp_path, rows=[])}
    )
    with (
        patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake),
        pytest.raises(CookieFetchError) as exc_info,
    ):
        await fetch_cookies_via_ssh(_ssh_cfg(), cache)
    assert "нет действующих кук" in str(exc_info.value)
    assert not cache.exists()


def test_remote_cookie_db_paths_relative_and_absolute(tmp_path: Path):
    relative = _remote_cookie_db_paths(tmp_path / "Profiles" / "abc123.default-release", tmp_path)
    assert relative == "AppData/Roaming/Mozilla/Firefox/Profiles/abc123.default-release/cookies.sqlite"
    absolute = _remote_cookie_db_paths(Path("C:/firefox"), tmp_path)
    assert absolute == "C:/firefox/cookies.sqlite"


def test_read_cookie_rows_filters_expired(tmp_path: Path):
    db = tmp_path / "cookies.sqlite"
    db.write_bytes(_cookie_db_bytes(tmp_path))
    rows = _read_cookie_rows(db, now=2000000000)
    assert [row.name for row in rows] == ["auth", "lid"]
    assert rows[0].secure is True and rows[0].http_only is True
    assert rows[1].host == ".vk.com"


def test_read_cookie_rows_corrupt_db_raises(tmp_path: Path):
    db = tmp_path / "cookies.sqlite"
    db.write_bytes(b"garbage")
    with pytest.raises(CookieFetchError):
        _read_cookie_rows(db)


def test_write_netscape_file_format(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    rows = [
        CookieRow(host="vk.com", path="/", secure=True, http_only=True, expiry=42, name="n", value="v"),
        CookieRow(host=".vk.com", path="/", secure=False, http_only=False, expiry=43, name="n2", value="v2"),
    ]
    _write_netscape_file(cache, rows)
    lines = cache.read_text(encoding="utf-8").strip().split("\n")
    assert lines[0] == "# Netscape HTTP Cookie File"
    assert lines[2] == "#HttpOnly_vk.com\tFALSE\t/\tTRUE\t42\tn\tv"
    assert lines[3] == ".vk.com\tTRUE\t/\tFALSE\t43\tn2\tv2"


@pytest.mark.asyncio
async def test_refresh_opens_tab_then_fetches(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    fake, captured = _fake_run({"profiles.ini": INI_TEXT.encode(), "cookies.sqlite": _cookie_db_bytes(tmp_path)})
    with patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake):
        result = await refresh_cookies_via_ssh(_ssh_cfg(), cache, wait_seconds=0)
    assert result == cache
    assert cache.read_text(encoding="utf-8").count("vk.com") >= 1
    first_command = captured[0]
    assert first_command[0] == "ssh"
    assert first_command[-1] == 'cmd /c start "" "firefox.exe" -headless -P "default-release" https://vk.com'


@pytest.mark.asyncio
async def test_refresh_tab_failure_propagates(tmp_path: Path):
    cache = tmp_path / "cookies.txt"
    fake, _captured = _fake_run({})  # no files: the tab-open ssh call succeeds, the ini scp fails
    with patch("src.reposter.utils.ssh_cookies._run_command", side_effect=fake), pytest.raises(CookieFetchError):
        await refresh_cookies_via_ssh(_ssh_cfg(), cache, wait_seconds=0)
