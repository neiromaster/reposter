# tests/test_main.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.__main__ import main


@pytest.mark.asyncio
async def test_main_with_debug():
    """Test the main function with the --debug flag."""
    # Arrange
    mock_composer = MagicMock()
    mock_app = AsyncMock()
    mock_composer.compose_app.return_value = mock_app

    with patch("sys.argv", ["__main__.py", "--debug"]), patch("pathlib.Path.exists", return_value=True):
        # Act
        await main(mock_composer)

        # Assert
        mock_composer.compose_app.assert_called_once_with(debug=True)
        mock_app.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_without_debug():
    """Test the main function without the --debug flag."""
    # Arrange
    mock_composer = MagicMock()
    mock_app = AsyncMock()
    mock_composer.compose_app.return_value = mock_app

    with patch("sys.argv", ["__main__.py"]), patch("pathlib.Path.exists", return_value=True):
        # Act
        await main(mock_composer)

        # Assert
        mock_composer.compose_app.assert_called_once_with(debug=False)
        mock_app.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_config_not_found():
    """Test the main function when config.yaml is not found."""
    # Arrange
    mock_composer = MagicMock()

    with (
        patch("sys.argv", ["__main__.py"]),
        patch("pathlib.Path.exists", return_value=False),
        patch("src.reposter.__main__.log") as mock_log,
        pytest.raises(SystemExit) as excinfo,
    ):
        # Act
        await main(mock_composer)

        # Assert
        assert excinfo.value.code == 1
        mock_log.assert_called_once_with("❌ Критическая ошибка: config.yaml не найден")


@pytest.mark.asyncio
async def test_main_app_run_exception():
    """Test the main function when app.run() raises an exception."""
    # Arrange
    mock_composer = MagicMock()
    mock_app = AsyncMock()
    mock_app.run.side_effect = Exception("Test exception")
    mock_composer.compose_app.return_value = mock_app

    with (
        patch("sys.argv", ["__main__.py"]),
        patch("pathlib.Path.exists", return_value=True),
        patch("src.reposter.__main__.log") as mock_log,
        pytest.raises(SystemExit) as excinfo,
    ):
        # Act
        await main(mock_composer)

        # Assert
        assert excinfo.value.code == 1
        mock_log.assert_called_once_with("❌ Критическая ошибка: Test exception")
