from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final, Literal, cast

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from ..utils.browser import CookieSpec, parse_cookies_spec
from ..utils.log import log

CHANNEL_ID_RE: Final[re.Pattern[str]] = re.compile(r"^(@[A-Za-z0-9_]+|-?\d+)$")


class AppConfig(BaseModel):
    wait_time_seconds: int = Field(default=600, ge=1)
    state_file: Path = Field(default=Path("state.yaml"))
    session_name: str = Field(default="user_session")


class VKConfig(BaseModel):
    domain: str = Field(..., min_length=1)
    post_count: int = Field(default=10, ge=1)
    post_source: Literal["wall", "donut"] = Field(default="wall")


class TelegramConfig(BaseModel):
    channel_ids: list[Any]

    @field_validator("channel_ids")
    @classmethod
    def validate_channel_ids(cls, v: list[Any]) -> list[str]:
        if not v:
            raise ValueError("Список channel_ids не может быть пустым")

        str_v = [str(ch) for ch in v]

        for ch in str_v:
            if not CHANNEL_ID_RE.match(ch):
                raise ValueError(f"Некорректный формат channel_id: {ch}. Используйте @username или числовой ID.")
        return str_v


class BoostyConfig(BaseModel):
    blog_name: str = Field(..., min_length=1)
    subscription_level_id: int | None = Field(default=None, ge=1)


class BindingConfig(BaseModel):
    vk: VKConfig
    telegram: TelegramConfig | None = None
    boosty: BoostyConfig | None = None

    @model_validator(mode="after")
    def check_at_least_one_target(self) -> BindingConfig:
        if self.telegram is None and self.boosty is None:
            raise ValueError("Должен быть указан хотя бы один таргет (telegram или boosty)")
        return self


class RetryConfig(BaseModel):
    count: int = Field(default=3, ge=0)
    delay_seconds: int = Field(default=10, ge=0)


class DownloaderConfig(BaseModel):
    browser: Literal["chrome", "firefox", "edge"] = Field(
        default="chrome",
        description="Устарело: используйте cookies_from_browser",
    )
    cookies_from_browser: str | None = Field(
        default=None,
        description="Спека как у --cookies-from-browser в yt-dlp: browser[:profile[:keyring[:container]]]",
    )
    output_path: Path = Field(default=Path("downloads"))
    yt_dlp_opts: dict[str, Any] = Field(default_factory=dict)
    retries: RetryConfig = Field(default_factory=RetryConfig)
    browser_restart_wait_seconds: int = Field(default=30, ge=0)

    @field_validator("cookies_from_browser")
    @classmethod
    def validate_cookies_from_browser(cls, v: str | None) -> str | None:
        """Fails fast on malformed specifications."""
        if v is not None:
            parse_cookies_spec(v)
        return v

    @property
    def cookie_spec(self) -> CookieSpec:
        """Parsed cookie source; falls back to the deprecated `browser` field."""
        if self.cookies_from_browser is not None:
            return parse_cookies_spec(self.cookies_from_browser)
        return CookieSpec(browser=self.browser)

    @field_validator("output_path")
    @classmethod
    def ensure_output_path_exists(cls, v: Path) -> Path:
        if not v.exists():
            v.mkdir(parents=True, exist_ok=True)
        return v


class Settings(BaseSettings):
    vk_service_token: str = Field(..., alias="VK_SERVICE_TOKEN")
    vk_user_token: str | None = Field(default=None, alias="VK_USER_TOKEN")
    telegram_api_id: int = Field(..., alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., alias="TELEGRAM_API_HASH")

    app: AppConfig = Field(default_factory=AppConfig)
    bindings: dict[str, BindingConfig]
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    class YamlConfigSource(PydanticBaseSettingsSource):
        yaml_path: Path
        _data: dict[str, Any]
        _last_mtime: float
        _file_read: bool = False

        def __init__(self, settings_cls: type[BaseSettings], yaml_path: Path) -> None:
            super().__init__(settings_cls)
            self.yaml_path = yaml_path
            self._data = {}
            self._last_mtime = 0.0

        def _file_changed(self) -> bool:
            """Checks if the file has been modified since the last load."""
            try:
                current_mtime = self.yaml_path.stat().st_mtime
                return current_mtime > self._last_mtime
            except OSError:
                return False

        def _read_yaml(self) -> dict[str, Any]:
            """Reads YAML only if the file has changed."""
            if self._file_read and not self._file_changed():
                return self._data

            if self.yaml_path.exists():
                try:
                    with open(self.yaml_path, encoding="utf-8") as f:
                        loaded = yaml.safe_load(f)
                        if isinstance(loaded, dict):
                            self._data = loaded
                            self._last_mtime = self.yaml_path.stat().st_mtime
                            self._file_read = True
                            log("🔁 Конфиг перезагружен из YAML")
                        else:
                            self._data = {}
                except Exception as e:
                    log(f"⚠️ Ошибка при чтении {self.yaml_path}: {e}")
            return self._data

        def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
            data = self._read_yaml()
            if field_name in data:
                return data[field_name], field_name, True
            return None, field_name, False

        def prepare_field_value(self, field_name: str, field: Any, value: Any, value_is_complex: bool) -> Any:
            return value

        def __call__(self) -> dict[str, Any]:
            return self._read_yaml()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            cls.YamlConfigSource(settings_cls, Path("config.yaml")),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def check_bindings_not_empty(self) -> Settings:
        if not self.bindings:
            raise ValueError("Словарь bindings не может быть пустым")
        return self

    @classmethod
    def load(cls) -> Settings:
        """Factory method for correct instantiation without arguments."""
        factory: type[Any] = cast(type[Any], cls)
        instance = factory()
        return cast(Settings, instance)


if __name__ == "__main__":
    settings = Settings.load()
    log(f"⚙️ {str(settings.model_dump())}")
