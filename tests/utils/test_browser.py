from pathlib import Path

import pytest

from src.reposter.utils.browser import CookieSpec, parse_cookies_spec


class TestParseCookiesSpec:
    def test_browser_only(self):
        assert parse_cookies_spec("firefox") == CookieSpec(browser="firefox")

    def test_browser_and_profile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        assert parse_cookies_spec("firefox:default-release-1") == CookieSpec(
            browser="firefox", profile="default-release-1"
        )

    def test_full_spec(self):
        assert parse_cookies_spec("chrome:Default:basic:shopping") == CookieSpec(
            browser="chrome", profile="Default", keyring="basic", container="shopping"
        )

    def test_empty_parts_become_none(self):
        assert parse_cookies_spec("firefox::") == CookieSpec(browser="firefox")

    def test_browser_case_normalized(self):
        assert parse_cookies_spec("Firefox:default").browser == "firefox"

    def test_existing_path_kept_whole(self, tmp_path: Path):
        parsed = parse_cookies_spec(f"firefox:{tmp_path}")
        assert parsed == CookieSpec(browser="firefox", profile=str(tmp_path))

    def test_missing_path_split_like_ytdlp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        # Не существующий путь — режем по ':' ровно как yt-dlp
        parsed = parse_cookies_spec(r"firefox:C:\nope\profile")
        assert parsed == CookieSpec(browser="firefox", profile="C", keyring=r"\nope\profile")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="пустой"):
            parse_cookies_spec("   ")

    def test_unknown_browser_rejected(self):
        with pytest.raises(ValueError, match="Неподдерживаемый браузер"):
            parse_cookies_spec("lynx:default")

    def test_too_many_parts_rejected(self):
        with pytest.raises(ValueError, match="Некорректный формат"):
            parse_cookies_spec("firefox:a:b:c:d")
