from pathlib import Path

import pytest

from src.reposter.utils.browser import CookieSpec, parse_cookies_spec, resolve_firefox_profile


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


INI_CONTENT = """
[General]
StartWithLastProfile=1
Version=2

[Profile0]
Name=default-release
IsRelative=1
Path=Profiles/urj13kw6.default-release
StoreID=4a201249
ShowSelector=0

[Profile3]
Name=default-release-2
IsRelative=1
Path=Profiles/7143b68p.default-release-2

[Profile2]
Name=default-release-1
IsRelative=1
Path=Profiles/ns5j57qn.default-release-1
StoreID=2a946dc1
ShowSelector=0

[Install71D58ADAB38A77EE]
Default=Profiles/7143b68p.default-release-2
Locked=1

[Profile1]
Name=default
IsRelative=1
Path=Profiles/p3asfmiv.default
Default=1

[Install308046B0AF4A39CB]
Default=Profiles/urj13kw6.default-release
Locked=1
"""


@pytest.fixture
def profiles_ini(tmp_path: Path) -> Path:
    ini = tmp_path / "profiles.ini"
    ini.write_text(INI_CONTENT, encoding="utf-8")
    return ini


class TestResolveFirefoxProfile:
    def test_resolves_by_name(self, profiles_ini: Path, tmp_path: Path):
        resolved = resolve_firefox_profile("default-release-1", ini_path=profiles_ini)
        assert resolved is not None
        assert resolved.name == "default-release-1"
        assert resolved.path == tmp_path / "Profiles" / "ns5j57qn.default-release-1"
        assert resolved.is_default is False

    def test_resolves_by_folder_name(self, profiles_ini: Path):
        resolved = resolve_firefox_profile("7143b68p.default-release-2", ini_path=profiles_ini)
        assert resolved is not None
        assert resolved.is_default is True  # install-default секции Install71D58ADAB38A77EE

    def test_resolves_marked_default(self, profiles_ini: Path):
        resolved = resolve_firefox_profile("default", ini_path=profiles_ini)
        assert resolved is not None
        assert resolved.is_default is True  # Default=1 в [Profile1]

    def test_unknown_value_returns_none(self, profiles_ini: Path):
        assert resolve_firefox_profile("no-such-profile", ini_path=profiles_ini) is None

    def test_absolute_path_value(self, profiles_ini: Path, tmp_path: Path):
        value = str(tmp_path / "Profiles" / "ns5j57qn.default-release-1")
        resolved = resolve_firefox_profile(value, ini_path=profiles_ini)
        assert resolved is not None
        assert resolved.name == "default-release-1"

    def test_existing_directory_fallback(self, tmp_path: Path):
        profile_dir = tmp_path / "custom-profile"
        profile_dir.mkdir()
        resolved = resolve_firefox_profile(str(profile_dir), ini_path=tmp_path / "missing.ini")
        assert resolved is not None
        assert resolved.name is None
        assert resolved.is_default is False

    def test_no_ini_and_missing_dir_returns_none(self, tmp_path: Path):
        assert resolve_firefox_profile("nope", ini_path=tmp_path / "missing.ini") is None

    def test_duplicate_section_ini_returns_none(self, tmp_path: Path):
        ini = tmp_path / "profiles.ini"
        duplicate = "\n[Profile0]\nName=default-release\nIsRelative=1\nPath=Profiles/urj13kw6.default-release\n"
        ini.write_text(INI_CONTENT + duplicate, encoding="utf-8")
        assert resolve_firefox_profile("default-release", ini_path=ini) is None

    def test_absolute_path_in_ini(self, tmp_path: Path):
        profile_dir = tmp_path / "absolute-profile"
        profile_dir.mkdir()
        ini = tmp_path / "profiles.ini"
        ini.write_text(f"[Profile0]\nName=abs\nIsRelative=0\nPath={profile_dir}\n", encoding="utf-8")
        resolved = resolve_firefox_profile("abs", ini_path=ini)
        assert resolved is not None
        assert resolved.path == profile_dir

    def test_resolves_by_relative_folder_path(self, profiles_ini: Path):
        resolved = resolve_firefox_profile("Profiles/ns5j57qn.default-release-1", ini_path=profiles_ini)
        assert resolved is not None
        assert resolved.name == "default-release-1"
