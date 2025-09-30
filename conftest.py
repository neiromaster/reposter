import sys
from pathlib import Path

import pytest


def pytest_configure(config):
    sys.path.insert(0, str(Path(__file__).parent / "src"))


@pytest.fixture
def settings(monkeypatch):
    """Sets dummy env vars and returns a loaded Settings object."""
    monkeypatch.setenv("VK_SERVICE_TOKEN", "test_vk_token")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "test_telegram_hash")
    from src.reposter.config.settings import Settings

    return Settings.load()
