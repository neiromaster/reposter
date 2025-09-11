from pathlib import Path
from typing import Optional

from ..config.settings import Settings
from ..utils.deep_diff import deep_diff


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
        if self._settings is None or self._file_changed():
            try:
                from ..config.settings import Settings

                new_settings = Settings.load()

                if self._settings is not None:
                    changes = deep_diff(self._settings, new_settings)
                    if changes:
                        print("📝 Обнаружены изменения в конфигурации:")
                        for change in changes:
                            print(f"   {change}")
                    else:
                        print("ℹ️ Конфиг изменился, но содержимое идентично.")

                self._settings = new_settings
                print("✅ Настройки перезагружены")
            except Exception as e:
                print(f"❌ Ошибка при перезагрузке конфига: {e}. Использую старую версию.")
                if self._settings is None:
                    raise
        return self._settings
