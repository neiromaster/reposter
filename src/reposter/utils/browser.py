"""Browser process and profile helpers for the downloader.

Parses yt-dlp style `--cookies-from-browser` specifications, resolves Firefox
profiles via profiles.ini, matches running browser processes to a profile and
closes browser processes cleanly.
"""

from __future__ import annotations

import configparser
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_COOKIE_SPEC_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<browser>[^:]+)"
    r"(?::(?P<profile>[^:]*)(?::(?P<keyring>[^:]*)(?::(?P<container>[^:]*))?)?)?$"
)

SUPPORTED_BROWSERS: Final[tuple[str, ...]] = ("chrome", "firefox", "edge")

_FIREFOX_NON_PROFILE_P_FLAGS: Final[frozenset[str]] = frozenset({"-ProfileManager", "-CreateProfile"})


@dataclass(frozen=True)
class CookieSpec:
    """Parsed cookies-from-browser specification: browser[:profile[:keyring[:container]]]."""

    browser: str
    profile: str | None = None
    keyring: str | None = None
    container: str | None = None


def parse_cookies_spec(spec: str) -> CookieSpec:
    """Parses a yt-dlp `--cookies-from-browser` style specification."""
    spec = spec.strip()
    if not spec:
        raise ValueError("cookies_from_browser не может быть пустой строкой")

    match = _COOKIE_SPEC_RE.match(spec)
    if not match:
        raise ValueError(
            f"Некорректный формат cookies_from_browser: {spec!r}. Ожидается browser[:profile[:keyring[:container]]]"
        )

    browser = match.group("browser").lower()
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(
            f"Неподдерживаемый браузер в cookies_from_browser: {browser!r}. Доступны: {', '.join(SUPPORTED_BROWSERS)}"
        )

    # Extension over yt-dlp: when the remainder after the browser points to an
    # existing directory, it is kept whole as the profile (Windows drive letters
    # like "C:\..." survive, yt-dlp would split them on ':').
    remainder = spec.split(":", 1)[1] if ":" in spec else ""
    if remainder and Path(remainder).is_dir():
        return CookieSpec(browser, remainder, None, None)

    return CookieSpec(
        browser,
        match.group("profile") or None,
        match.group("keyring") or None,
        match.group("container") or None,
    )


@dataclass(frozen=True)
class ResolvedFirefoxProfile:
    """A Firefox profile resolved to an absolute path via profiles.ini or the filesystem."""

    path: Path
    name: str | None
    is_default: bool


def _firefox_profiles_ini_paths() -> tuple[Path, ...]:
    if sys.platform in ("cygwin", "win32"):
        return (Path(os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\profiles.ini")),)
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "Firefox" / "profiles.ini",)
    return (
        Path.home() / ".mozilla" / "firefox" / "profiles.ini",
        Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox" / "profiles.ini",
        Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox" / "profiles.ini",
    )


def _ini_relative_path(ini_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ini_dir / path


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _read_profiles_ini(ini_path: Path) -> tuple[tuple[Path, ...], list[tuple[str | None, Path, bool]]]:
    """Returns (install_default_paths, [(name, path, marked_default), ...])."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # preserve key case (Name/Path/Default)
    parser.read(ini_path, encoding="utf-8-sig")

    install_defaults: list[Path] = []
    profiles: list[tuple[str | None, Path, bool]] = []
    for section in parser.sections():
        if section.startswith("Install"):
            raw = parser.get(section, "Default", fallback=None)
            if raw:
                install_defaults.append(_ini_relative_path(ini_path.parent, raw))
        elif section.startswith("Profile"):
            name = parser.get(section, "Name", fallback=None)
            raw_path = parser.get(section, "Path", fallback=None)
            if not raw_path:
                continue
            relative = parser.getboolean(section, "IsRelative", fallback=True)
            path = _ini_relative_path(ini_path.parent, raw_path) if relative else Path(raw_path)
            marked_default = parser.getboolean(section, "Default", fallback=False)
            profiles.append((name, path, marked_default))
    return tuple(install_defaults), profiles


def resolve_firefox_profile(value: str, ini_path: Path | None = None) -> ResolvedFirefoxProfile | None:
    """Resolves a Firefox profile given as a profiles.ini name, folder name or path.

    Falls back to treating the value as an existing directory. Returns None when
    nothing matches.
    """
    if not value.strip():
        return None
    candidates = (ini_path,) if ini_path is not None else _firefox_profiles_ini_paths()
    # normcase() rewrites '/' to '\' on Windows, so convert back to '/' for comparison.
    value_norm = os.path.normcase(value.strip().replace("\\", "/").strip("/")).replace("\\", "/")

    for ini in candidates:
        if not ini.is_file():
            continue
        try:
            install_defaults, profiles = _read_profiles_ini(ini)
        except configparser.Error:
            continue
        for name, path, marked_default in profiles:
            path_norm = os.path.normcase(str(path)).replace("\\", "/")
            name_match = name is not None and os.path.normcase(name) == value_norm
            path_match = path_norm == value_norm or path_norm.endswith("/" + value_norm)
            if not (name_match or path_match):
                continue
            is_default = marked_default or any(_same_path(d, path) for d in install_defaults)
            return ResolvedFirefoxProfile(path, name, is_default)

    direct = Path(value)
    if direct.is_dir():
        return ResolvedFirefoxProfile(direct.resolve(), None, False)
    return None


def firefox_profile_args(argv: list[str]) -> list[str]:
    """Extracts profile values from a Firefox command line (-P name, -p name, --profile path, --profile=path).

    The joined -Pname form and the lowercase -p are kept as defensive parsing,
    not real Firefox grammar. Empty values are skipped: Firefox ignores a bare
    --profile= and launches the default profile.
    """
    values: list[str] = []
    for i, arg in enumerate(argv):
        if arg in _FIREFOX_NON_PROFILE_P_FLAGS:
            continue
        value: str | None = None
        if arg in ("-P", "-p", "--profile") and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("-P") and len(arg) > 2:
            value = arg[2:]
        elif arg.startswith("--profile="):
            value = arg.split("=", 1)[1]
        if value is not None and value.strip():
            values.append(value)
    return values


def is_firefox_main_process(argv: list[str]) -> bool:
    """Firefox content (child) processes are spawned with -contentproc on their command line."""
    return "-contentproc" not in argv


def matches_firefox_profile_argv(argv: list[str], resolved: ResolvedFirefoxProfile) -> bool:
    """True when the command line belongs to a main Firefox process running the resolved profile."""
    if not is_firefox_main_process(argv):
        return False

    profile_values = firefox_profile_args(argv)
    if not profile_values:
        # A profile-less launch opens the install-default profile. Known
        # limitation: with multiple installs every install-default matches
        # (no default-install registry lookup here).
        return resolved.is_default

    for value in profile_values:
        candidate = resolve_firefox_profile(value)
        if candidate is not None:
            if _same_path(candidate.path, resolved.path):
                return True
        elif _same_path(Path(value), resolved.path):
            return True
    return False
