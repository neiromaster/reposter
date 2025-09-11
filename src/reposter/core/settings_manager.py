from pathlib import Path
from typing import Optional

from ..config.settings import Settings


class SettingsManager:
    """
    Settings manager with support for dynamic reloading.
    Ensures that the current version of settings is returned for each request.
    """

    _instance: Optional["SettingsManager"] = None
    _settings: Optional["Settings"] = None
    _config_path: Path
    _last_mtime: float = 0.0

    def __new__(cls, config_path: str = "config.yaml") -> "SettingsManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config_path = Path(config_path)
        return cls._instance

    def _file_changed(self) -> bool:
        try:
            current_mtime = self._config_path.stat().st_mtime
            if current_mtime > self._last_mtime:
                self._last_mtime = current_mtime
                return True
        except OSError:
            pass
        return False

    def get_settings(self) -> "Settings":
        """
        Returns the current settings.
        If the file has changed, it recreates the Settings instance.
        """
        if self._settings is None or self._file_changed():
            from ..config.settings import Settings  # lazy import to avoid circular

            self._settings = Settings.load()
            print("✅ Настройки перезагружены")
        return self._settings
