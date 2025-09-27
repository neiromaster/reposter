# type: ignore[reportPrivateUsage]
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from _pytest.monkeypatch import MonkeyPatch
from pydantic import ValidationError

from src.reposter.config.settings import (
    BindingConfig,
    BoostyConfig,
    DownloaderConfig,
    RetryConfig,
    Settings,
    TelegramConfig,
    VKConfig,
)


class TestSettingsValidation:
    def test_telegram_config_empty_channel_ids(self):
        """Test validation error when telegram channel_ids is empty."""
        with pytest.raises(ValidationError) as exc_info:
            TelegramConfig(channel_ids=[])

        assert "Список channel_ids не может быть пустым" in str(exc_info.value)

    def test_telegram_config_invalid_channel_ids(self):
        """Test validation error when telegram channel_ids are invalid."""
        with pytest.raises(ValidationError) as exc_info:
            TelegramConfig(channel_ids=["invalid_channel"])

        assert "Некорректный формат channel_id" in str(exc_info.value)

    def test_binding_config_no_targets(self):
        """Test validation error when binding has no targets."""
        with pytest.raises(ValidationError) as exc_info:
            BindingConfig(vk=VKConfig(domain="test", post_count=5, post_source="wall"))

        assert "Должен быть указан хотя бы один таргет" in str(exc_info.value)

    def test_settings_empty_bindings(self, monkeypatch: MonkeyPatch):
        """Test validation error when settings have empty bindings."""
        # Mock environment variables
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")

        with pytest.raises(ValidationError) as exc_info:
            Settings(bindings=[])  # type: ignore[call-arg]

        assert "Список bindings не может быть пустым" in str(exc_info.value)

    def test_vk_config_domain_min_length(self):
        """Test validation error when VK config domain has min length."""
        with pytest.raises(ValidationError):
            VKConfig(domain="", post_count=5, post_source="wall")

    def test_boosty_config_blog_name_min_length(self):
        """Test validation error when Boosty config blog_name has min length."""
        with pytest.raises(ValidationError):
            BoostyConfig(blog_name="")

    def test_boosty_config_subscription_level_ge(self):
        """Test validation error when subscription_level_id is less than 1."""
        with pytest.raises(ValidationError):
            BoostyConfig(blog_name="test", subscription_level_id=0)

    def test_retry_config_count_ge(self):
        """Test validation error when retry count is less than 0."""
        from src.reposter.config.settings import RetryConfig

        with pytest.raises(ValidationError):
            RetryConfig(count=-1)

    def test_retry_config_delay_ge(self):
        """Test validation error when retry delay is less than 0."""
        with pytest.raises(ValidationError):
            RetryConfig(delay_seconds=-1)

    def test_downloader_config_output_path_exists(self):
        """Test that downloader config creates output path if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_path = Path(temp_dir) / "new_dir"
            config = DownloaderConfig(output_path=non_existent_path)
            # This should succeed and create the directory
            assert config.output_path.exists()

    def test_settings_valid_creation(self, monkeypatch: MonkeyPatch):
        """Test creating valid settings."""
        # Mock the YAML config source to avoid loading from file
        monkeypatch.setenv("VK_SERVICE_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "test_hash")

        # The Settings class loads from environment variables and YAML
        # We need to set the required environment variables
        settings = Settings(
            bindings=[
                BindingConfig(
                    vk=VKConfig(domain="test", post_count=5, post_source="wall"),
                    telegram=TelegramConfig(channel_ids=["@test_channel"]),
                )
            ],
        )  # type: ignore[call-arg]
        # Check that the bindings were correctly set
        assert len(settings.bindings) == 1

    def test_binding_config_with_telegram_only(self):
        """Test binding config with only telegram target."""
        binding = BindingConfig(
            vk=VKConfig(domain="test", post_count=5, post_source="wall"),
            telegram=TelegramConfig(channel_ids=["@test_channel"]),
        )
        assert binding.telegram is not None
        assert binding.boosty is None

    def test_binding_config_with_boosty_only(self):
        """Test binding config with only boosty target."""
        binding = BindingConfig(
            vk=VKConfig(domain="test", post_count=5, post_source="wall"), boosty=BoostyConfig(blog_name="test_blog")
        )
        assert binding.boosty is not None
        assert binding.telegram is None

    def test_binding_config_with_both_targets(self):
        """Test binding config with both telegram and boosty targets."""
        binding = BindingConfig(
            vk=VKConfig(domain="test", post_count=5, post_source="wall"),
            telegram=TelegramConfig(channel_ids=["@test_channel"]),
            boosty=BoostyConfig(blog_name="test_blog"),
        )
        assert binding.telegram is not None
        assert binding.boosty is not None


class TestYamlConfigSource:
    @pytest.fixture
    def mock_settings_cls(self):
        """Fixture for a mock settings class."""
        return type("MockSettings", (Settings,), {})

    def test_file_changed_os_error(self, mock_settings_cls: type[Settings], tmp_path: Path):
        """Test that _file_changed returns False on OSError."""
        # Arrange
        yaml_path = tmp_path / "config.yaml"
        source = Settings.YamlConfigSource(mock_settings_cls, yaml_path)
        with patch("pathlib.Path.stat", side_effect=OSError):
            # Act & Assert
            assert not source._file_changed()

    def test_read_yaml_not_a_dict(self, mock_settings_cls: type[Settings], tmp_path: Path):
        """Test that _read_yaml returns an empty dict if YAML is not a dict."""
        # Arrange
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("not a dict")
        source = Settings.YamlConfigSource(mock_settings_cls, yaml_path)
        # Act
        data = source._read_yaml()
        # Assert
        assert data == {}

    def test_read_yaml_exception(self, mock_settings_cls: type[Settings], tmp_path: Path):
        """Test that _read_yaml returns an empty dict on exception."""
        # Arrange
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("invalid: yaml: here")
        source = Settings.YamlConfigSource(mock_settings_cls, yaml_path)
        # Act
        data = source._read_yaml()
        # Assert
        assert data == {}

    def test_get_field_value_not_in_data(self, mock_settings_cls: type[Settings], tmp_path: Path):
        """Test get_field_value when the field is not in the data."""
        # Arrange
        yaml_path = tmp_path / "config.yaml"
        source = Settings.YamlConfigSource(mock_settings_cls, yaml_path)
        with patch.object(source, "_read_yaml", return_value={}):
            # Act
            value, _, is_complex = source.get_field_value(None, "some_field")
            # Assert
            assert value is None
            assert not is_complex

    def test_file_not_changed(self, mock_settings_cls: type[Settings], tmp_path: Path):
        """Test that the YAML file is not re-read if it hasn't changed."""
        # Arrange
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("app: {wait_time_seconds: 120}")
        source = Settings.YamlConfigSource(mock_settings_cls, yaml_path)

        # Act
        first_read = source._read_yaml()
        second_read = source._read_yaml()

        # Assert
        assert first_read is second_read
