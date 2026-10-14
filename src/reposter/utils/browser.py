"""Browser process and profile helpers for the downloader.

Parses yt-dlp style `--cookies-from-browser` specifications, resolves Firefox
profiles via profiles.ini, matches running browser processes to a profile and
closes browser processes cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_COOKIE_SPEC_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<browser>[^:]+)"
    r"(?::(?P<profile>[^:]*)(?::(?P<keyring>[^:]*)(?::(?P<container>[^:]*))?)?)?$"
)

SUPPORTED_BROWSERS: Final[tuple[str, ...]] = ("chrome", "firefox", "edge")


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
