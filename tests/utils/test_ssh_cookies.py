# pyright: reportPrivateUsage=false
from pathlib import Path
from typing import Any

from src.reposter.config.settings import CookiesViaSshConfig
from src.reposter.utils.ssh_cookies import (
    _build_open_tab_command,
    _build_scp_command,
    _build_ssh_command,
    cookies_cache_path,
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
