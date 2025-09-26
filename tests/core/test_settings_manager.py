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