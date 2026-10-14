import sys
from pathlib import Path
from unittest.mock import Mock, patch

import psutil
import pytest

from src.reposter.utils import browser as browser_module
from src.reposter.utils.browser import (
    CookieSpec,
    ResolvedFirefoxProfile,
    close_process_gracefully,
    close_process_tree_gracefully,
    firefox_profile_args,
    is_firefox_main_process,
    matches_firefox_profile_argv,
    parse_cookies_spec,
    resolve_firefox_profile,
)


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


class TestFirefoxProfileArgs:
    def test_dash_p_with_value(self):
        assert firefox_profile_args(["firefox.exe", "-P", "work"]) == ["work"]

    def test_dash_p_joined(self):
        assert firefox_profile_args(["firefox.exe", "-Pwork"]) == ["work"]

    def test_double_dash_profile(self):
        assert firefox_profile_args(["firefox.exe", "--profile", r"C:\prof"]) == [r"C:\prof"]

    def test_double_dash_profile_eq(self):
        assert firefox_profile_args(["firefox.exe", r"--profile=C:\prof"]) == [r"C:\prof"]

    def test_profile_manager_ignored(self):
        assert firefox_profile_args(["firefox.exe", "-ProfileManager"]) == []

    def test_no_profile_args(self):
        assert firefox_profile_args(["firefox.exe", "-no-remote"]) == []

    def test_lowercase_p_accepted(self):
        assert firefox_profile_args(["firefox.exe", "-p", "work"]) == ["work"]

    def test_create_profile_next_arg_not_swallowed(self):
        assert firefox_profile_args(["firefox.exe", "-CreateProfile", "newprof"]) == []

    def test_final_p_token_without_value(self):
        assert firefox_profile_args(["firefox.exe", "-P"]) == []

    def test_empty_profile_value_skipped(self):
        assert firefox_profile_args(["firefox.exe", "--profile="]) == []


class TestIsFirefoxMainProcess:
    def test_main_process(self):
        assert is_firefox_main_process(["firefox.exe"]) is True

    def test_content_proc_child(self):
        assert is_firefox_main_process(["firefox.exe", "-contentproc", "12", "parentBuildID"]) is False


class TestMatchesFirefoxProfileArgv:
    @pytest.fixture
    def resolved(self) -> ResolvedFirefoxProfile:
        return ResolvedFirefoxProfile(
            path=Path(r"C:\Users\t\AppData\Roaming\Mozilla\Firefox\Profiles\ns5j57qn.default-release-1"),
            name="default-release-1",
            is_default=False,
        )

    @pytest.fixture
    def resolved_default(self) -> ResolvedFirefoxProfile:
        return ResolvedFirefoxProfile(path=Path(r"C:\prof\p.default"), name="p.default", is_default=True)

    def test_flagged_instance_matches(self, resolved: ResolvedFirefoxProfile, monkeypatch):
        monkeypatch.setattr(
            browser_module,
            "resolve_firefox_profile",
            lambda value, ini_path=None: resolved if value == "default-release-1" else None,
        )
        argv = ["firefox.exe", "-P", "default-release-1"]
        assert matches_firefox_profile_argv(argv, resolved) is True

    def test_other_profile_flag_does_not_match(self, resolved: ResolvedFirefoxProfile, monkeypatch):
        monkeypatch.setattr(browser_module, "resolve_firefox_profile", lambda value, ini_path=None: None)
        argv = ["firefox.exe", "-P", "default-release-2"]
        assert matches_firefox_profile_argv(argv, resolved) is False

    def test_profile_path_flag_matches(self, resolved: ResolvedFirefoxProfile, monkeypatch):
        monkeypatch.setattr(browser_module, "resolve_firefox_profile", lambda value, ini_path=None: None)
        argv = ["firefox.exe", "--profile", str(resolved.path)]
        assert matches_firefox_profile_argv(argv, resolved) is True

    def test_child_process_never_matches(self, resolved: ResolvedFirefoxProfile, monkeypatch):
        monkeypatch.setattr(browser_module, "resolve_firefox_profile", lambda value, ini_path=None: None)
        argv = ["firefox.exe", "-contentproc", "1", "-P", "default-release-1"]
        assert matches_firefox_profile_argv(argv, resolved) is False

    def test_flagless_non_default_not_matched(self, resolved: ResolvedFirefoxProfile):
        assert matches_firefox_profile_argv(["firefox.exe"], resolved) is False

    def test_flagless_default_matched(self, resolved_default: ResolvedFirefoxProfile):
        assert matches_firefox_profile_argv(["firefox.exe"], resolved_default) is True

    @pytest.mark.skipif(sys.platform != "win32", reason="normcase folds case only on Windows")
    def test_profile_path_flag_case_insensitive_on_windows(self, resolved: ResolvedFirefoxProfile, monkeypatch):
        monkeypatch.setattr(browser_module, "resolve_firefox_profile", lambda value, ini_path=None: None)
        argv = ["firefox.exe", "--profile", str(resolved.path).upper()]
        assert matches_firefox_profile_argv(argv, resolved) is True


class TestCloseProcessGracefully:
    def test_uses_taskkill_then_waits(self):
        proc = Mock()
        proc.pid = 123
        proc.wait = Mock()
        with patch("subprocess.run") as mock_run:
            close_process_gracefully(proc)
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["taskkill", "/PID", "123"]
        proc.kill.assert_not_called()

    def test_kills_after_timeout(self):
        proc = Mock()
        proc.pid = 123
        proc.wait = Mock(side_effect=[psutil.TimeoutExpired(123), None])
        with patch("subprocess.run"):
            close_process_gracefully(proc, timeout=0.01)
        proc.kill.assert_called_once()

    def test_process_disappearing_is_not_an_error(self):
        proc = Mock()
        proc.pid = 5
        proc.wait = Mock(side_effect=psutil.NoSuchProcess(5))
        with patch("subprocess.run"):
            close_process_gracefully(proc)  # must not raise

    def test_kill_fallback_failure_does_not_raise(self):
        proc = Mock()
        proc.pid = 123
        proc.wait = Mock(side_effect=[psutil.TimeoutExpired(123), psutil.TimeoutExpired(123)])
        proc.kill = Mock(side_effect=psutil.AccessDenied(123))
        with patch("subprocess.run"):
            close_process_gracefully(proc, timeout=0.01)  # must not raise
        proc.kill.assert_called_once()

    def test_posix_terminates_without_taskkill(self):
        proc = Mock()
        proc.pid = 123
        proc.wait = Mock()
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
            close_process_gracefully(proc)
        proc.terminate.assert_called_once()
        mock_run.assert_not_called()


class TestCloseProcessTreeGracefully:
    def test_closes_children_too(self):
        child = Mock()
        child.pid = 2
        child.wait = Mock()
        proc = Mock()
        proc.pid = 1
        proc.children.return_value = [child]
        proc.wait = Mock()
        with patch("subprocess.run"):
            close_process_tree_gracefully(proc)
        child.kill.assert_not_called()  # child exits on its own after parent close
        proc.wait.assert_called()

    def test_children_closed_when_parent_hangs(self):
        child = Mock()
        child.pid = 2
        child.wait = Mock()
        proc = Mock()
        proc.pid = 1
        proc.children.return_value = [child]
        proc.wait = Mock(side_effect=[psutil.TimeoutExpired(1), None])
        with patch("subprocess.run"):
            close_process_tree_gracefully(proc, timeout=0.01)
        child.wait.assert_called()  # child still closed even though the parent needed the kill fallback

    def test_children_error_is_swallowed(self):
        proc = Mock()
        proc.pid = 1
        proc.children.side_effect = psutil.AccessDenied(1)
        proc.wait = Mock()
        with patch("subprocess.run"):
            close_process_tree_gracefully(proc)  # must not raise
