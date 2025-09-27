# type: ignore[reportPrivateUsage]
from unittest.mock import MagicMock, patch

import pytest

from src.reposter.core.settings_manager import SettingsManager


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton instance before each test."""
    SettingsManager._instance = None


def test_singleton():
    """Test that SettingsManager is a singleton."""
    # Arrange
    sm1 = SettingsManager()
    sm2 = SettingsManager()

    # Assert
    assert sm1 is sm2


def test_file_changed_true():
    """Test _file_changed when the file has been modified."""
    # Arrange
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_mtime = 2.0
        sm = SettingsManager()
        sm._last_mtime = 1.0

        # Act
        result = sm._file_changed()

        # Assert
        assert result is True


def test_file_changed_false():
    """Test _file_changed when the file has not been modified."""
    # Arrange
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_mtime = 1.0
        sm = SettingsManager()
        sm._last_mtime = 1.0

        # Act
        result = sm._file_changed()

        # Assert
        assert result is False


def test_get_settings_first_call():
    """Test get_settings on the first call."""
    # Arrange
    with patch("src.reposter.config.settings.Settings.load") as mock_load, patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_mtime = 1.0
        sm = SettingsManager()

        # Act
        settings = sm.get_settings()

        # Assert
        mock_load.assert_called_once()
        assert settings is not None


def test_get_settings_file_changed():
    """Test get_settings when the file has changed."""
    # Arrange
    with patch("src.reposter.config.settings.Settings.load") as mock_load, patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_mtime = 2.0
        sm = SettingsManager()
        sm._last_mtime = 1.0

        # Act
        sm.get_settings()

        # Assert
        mock_load.assert_called_once()


def test_get_settings_file_not_changed():
    """Test get_settings when the file has not changed."""
    # Arrange
    with patch("src.reposter.config.settings.Settings.load") as mock_load, patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_mtime = 1.0
        sm = SettingsManager()
        sm._settings = MagicMock()
        sm._last_mtime = 1.0

        # Act
        settings = sm.get_settings()

        # Assert
        mock_load.assert_not_called()
        assert settings is not None


def test_get_settings_invalid_file():
    """Test get_settings when the config file is invalid."""
    # Arrange
    with (
        patch("src.reposter.config.settings.Settings.load", side_effect=Exception("Test exception")),
        patch("pathlib.Path.stat") as mock_stat,
        pytest.raises(Exception, match="Test exception"),
    ):
        mock_stat.return_value.st_mtime = 1.0
        sm = SettingsManager()
        sm._settings = None

        # Act
        sm.get_settings()


@pytest.fixture
def mock_log():
    """Fixture for mocking log."""
    with patch("src.reposter.core.settings_manager.log") as mock_log:
        yield mock_log


def test_file_changed_os_error(mock_log: MagicMock):
    """Test _file_changed when os error occurs."""
    # Arrange
    with patch("pathlib.Path.stat", side_effect=OSError("Test error")):
        sm = SettingsManager()

        # Act
        result = sm._file_changed()

        # Assert
        assert result is False


def test_get_settings_with_changes(mock_log: MagicMock):
    """Test get_settings when the file has changed and there are differences."""
    # Arrange
    with (
        patch("src.reposter.config.settings.Settings.load") as mock_load,
        patch("pathlib.Path.stat") as mock_stat,
        patch("src.reposter.core.settings_manager.deep_diff") as mock_deep_diff,
    ):
        mock_stat.return_value.st_mtime = 2.0
        mock_deep_diff.return_value = ["change1", "change2"]
        sm = SettingsManager()
        sm._settings = MagicMock()
        sm._last_mtime = 1.0

        # Act
        sm.get_settings()

        # Assert
        mock_load.assert_called_once()
        mock_log.assert_any_call("📝 Обнаружены изменения в конфигурации:")
        mock_log.assert_any_call("change1", indent=2)
        mock_log.assert_any_call("change2", indent=2)


def test_get_settings_no_changes(mock_log: MagicMock):
    """Test get_settings when the file has changed but there are no differences."""
    # Arrange
    with (
        patch("src.reposter.config.settings.Settings.load") as mock_load,
        patch("pathlib.Path.stat") as mock_stat,
        patch("src.reposter.core.settings_manager.deep_diff") as mock_deep_diff,
    ):
        mock_stat.return_value.st_mtime = 2.0
        mock_deep_diff.return_value = []
        sm = SettingsManager()
        sm._settings = MagicMock()
        sm._last_mtime = 1.0

        # Act
        sm.get_settings()

        # Assert
        mock_load.assert_called_once()
        mock_log.assert_any_call("ℹ️ Конфиг изменился, но содержимое идентично.")


def test_get_settings_reload_fails(mock_log: MagicMock):
    """Test get_settings when reloading fails."""
    # Arrange
    with (
        patch("src.reposter.config.settings.Settings.load", side_effect=Exception("Test exception")) as mock_load,
        patch("pathlib.Path.stat") as mock_stat,
    ):
        mock_stat.return_value.st_mtime = 2.0
        sm = SettingsManager()
        original_settings = MagicMock()
        sm._settings = original_settings
        sm._last_mtime = 1.0

        # Act
        settings = sm.get_settings()

        # Assert
        mock_load.assert_called_once()
        mock_log.assert_any_call("❌ Ошибка при перезагрузке конфига: Test exception. Использую старую версию.")
        assert settings is original_settings
