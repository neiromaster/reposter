import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
import tenacity
from pydantic import HttpUrl

from src.reposter.config.settings import Settings
from src.reposter.managers.vk_manager import VKManager
from src.reposter.models.dto import Post, VKAPIResponseDict


@pytest.fixture
def settings() -> Settings:
    mock_settings = MagicMock(spec=Settings)
    mock_settings.vk_service_token = "mock_token"
    return mock_settings


@pytest.fixture
async def vk_manager() -> AsyncGenerator[VKManager, None]:
    manager = VKManager()
    shutdown_event = asyncio.Event()
    manager.set_shutdown_event(shutdown_event)
    yield manager
    if manager._initialized:  # type: ignore[reportPrivateUsage]
        await manager.shutdown()


@pytest.mark.asyncio
async def test_setup_initializes_client(vk_manager: VKManager, settings: Settings):
    assert not vk_manager._initialized  # type: ignore[reportPrivateUsage]
    assert vk_manager._client is None  # type: ignore[reportPrivateUsage]

    await vk_manager.setup(settings)

    assert vk_manager._initialized  # type: ignore[reportPrivateUsage]
    assert vk_manager._client is not None  # type: ignore[reportPrivateUsage]
    assert vk_manager._token == "mock_token"  # type: ignore[reportPrivateUsage]
    assert not vk_manager._shutdown_event.is_set()  # type: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_setup_reinitializes_if_already_initialized(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)
    old_client = vk_manager._client  # type: ignore[reportPrivateUsage]

    await vk_manager.setup(settings)

    assert vk_manager._client is not None  # type: ignore[reportPrivateUsage]
    assert vk_manager._client != old_client  # новый клиент создан  # type: ignore[reportPrivateUsage]
    assert vk_manager._initialized  # type: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_update_config_calls_setup_if_not_initialized(vk_manager: VKManager, settings: Settings):
    with patch.object(vk_manager, "setup", new_callable=AsyncMock) as mock_setup:
        await vk_manager.update_config(settings)
        mock_setup.assert_awaited_once_with(settings)


@pytest.mark.asyncio
async def test_update_config_restarts_if_token_changed(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)

    settings.vk_service_token = "new_token"
    with (
        patch.object(vk_manager, "shutdown", new_callable=AsyncMock) as mock_shutdown,
        patch.object(vk_manager, "setup", new_callable=AsyncMock) as mock_setup,
    ):
        await vk_manager.update_config(settings)
        mock_shutdown.assert_awaited_once()
        mock_setup.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_config_does_nothing_if_token_same(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)

    with (
        patch.object(vk_manager, "shutdown", new_callable=AsyncMock) as mock_shutdown,
        patch.object(vk_manager, "setup", new_callable=AsyncMock) as mock_setup,
    ):
        await vk_manager.update_config(settings)
        mock_shutdown.assert_not_awaited()
        mock_setup.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_closes_client(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)
    mock_client = vk_manager._client  # type: ignore[reportPrivateUsage]
    if mock_client:
        mock_client.aclose = AsyncMock()

    await vk_manager.shutdown()

    assert not vk_manager._initialized  # type: ignore[reportPrivateUsage]
    if mock_client:
        cast(AsyncMock, mock_client.aclose).assert_awaited_once()


@pytest.mark.asyncio
async def test_should_retry_respects_shutdown(vk_manager: VKManager):
    vk_manager._shutdown_event.set()  # type: ignore[reportPrivateUsage]
    retry_state = MagicMock()
    retry_state.outcome = None

    result = await vk_manager._should_retry(retry_state)  # type: ignore[reportPrivateUsage]
    assert result is False


@pytest.mark.asyncio
async def test_should_retry_ignores_cancelled_error(vk_manager: VKManager):
    retry_state = MagicMock()
    retry_state.outcome.exception.return_value = asyncio.CancelledError()

    result = await vk_manager._should_retry(retry_state)  # type: ignore[reportPrivateUsage]
    assert result is False


@pytest.mark.asyncio
async def test_should_retry_accepts_http_errors(vk_manager: VKManager):
    retry_state = MagicMock()
    retry_state.outcome.exception.return_value = httpx.RequestError("mock")

    result = await vk_manager._should_retry(retry_state)  # type: ignore[reportPrivateUsage]
    assert result is True


@pytest.mark.asyncio
@respx.mock
async def test_download_file_success(vk_manager: VKManager, settings: Settings, tmp_path: Path):
    await vk_manager.setup(settings)

    url = HttpUrl("https://example.com/test.jpg")
    content = b"fake image content"

    respx.get(str(url)).respond(content=content)  # type: ignore

    result = await vk_manager.download_file(url, tmp_path)

    assert result is not None
    assert result.name == "test.jpg"
    assert result.read_bytes() == content


@pytest.mark.asyncio
@respx.mock
async def test_download_file_invalid_url(vk_manager: VKManager, settings: Settings, tmp_path: Path):
    await vk_manager.setup(settings)

    url = HttpUrl("https://example.com/")  # no path

    result = await vk_manager.download_file(url, tmp_path)

    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_download_file_interrupted(vk_manager: VKManager, settings: Settings, tmp_path: Path):
    await vk_manager.setup(settings)

    url = HttpUrl("https://example.com/test.jpg")

    # Simulate cancellation during download
    async def _streaming_side_effect(*args: object, **kwargs: object):
        raise asyncio.CancelledError("Simulated cancellation")

    route = respx.get(str(url))
    route.mock(side_effect=_streaming_side_effect)

    with pytest.raises(asyncio.CancelledError):
        await vk_manager.download_file(url, tmp_path)

    # Ensure no partial file remains
    assert not (tmp_path / "test.jpg").exists()


@pytest.mark.asyncio
@respx.mock
async def test_get_vk_wall_success(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)

    mock_response: VKAPIResponseDict = {
        "response": {
            "count": 1,
            "items": [
                {
                    "id": 123,
                    "owner_id": -12345,
                    "from_id": -12345,
                    "text": "Hello world",
                    "date": 1700000000,
                    "attachments": [],
                }
            ],
        }
    }

    respx.get("https://api.vk.com/method/wall.get").respond(json=cast(dict[str, object], mock_response))  # type: ignore

    posts = await vk_manager.get_vk_wall("example", 5, "wall")

    assert len(posts) == 1
    assert isinstance(posts[0], Post)
    assert posts[0].text == "Hello world"


@pytest.mark.asyncio
@respx.mock
async def test_get_vk_wall_with_dont_filter(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)

    mock_response: VKAPIResponseDict = {"response": {"count": 0, "items": []}}
    route = respx.get("https://api.vk.com/method/wall.get").respond(  # type: ignore
        json=cast(dict[str, object], mock_response)
    )

    await vk_manager.get_vk_wall("example", 5, "donut")

    # Check that 'filter=donut' was passed
    request: httpx.Request = route.calls[0].request  # type: ignore
    assert "filter" in request.url.params  # type: ignore
    assert request.url.params["filter"] == "donut"  # type: ignore


@pytest.mark.asyncio
@respx.mock
async def test_get_vk_wall_api_error(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)

    error_response = {"error": {"error_code": 5, "error_msg": "Access denied"}}

    respx.get("https://api.vk.com/method/wall.get").respond(json=error_response)  # type: ignore

    with pytest.raises(tenacity.RetryError):
        await vk_manager.get_vk_wall("example", 5, "wall")


@pytest.mark.asyncio
@respx.mock
async def test_get_vk_wall_empty_response(vk_manager: VKManager, settings: Settings):
    await vk_manager.setup(settings)

    respx.get("https://api.vk.com/method/wall.get").respond(json={})  # type: ignore

    with pytest.raises(ValueError, match="VK API response is empty or invalid"):
        await vk_manager.get_vk_wall("example", 5, "wall")


@pytest.mark.asyncio
async def test_get_vk_wall_not_initialized(vk_manager: VKManager):
    with pytest.raises(tenacity.RetryError):
        await vk_manager.get_vk_wall("example", 5, "wall")


@pytest.mark.asyncio
async def test_download_file_not_initialized(vk_manager: VKManager):
    url = HttpUrl("https://example.com/test.jpg")
    with pytest.raises(tenacity.RetryError):
        await vk_manager.download_file(url, Path("/tmp"))


@pytest.mark.asyncio
@respx.mock
async def test_download_file_http_error_triggers_retry(vk_manager: VKManager, settings: Settings, tmp_path: Path):
    await vk_manager.setup(settings)

    url = HttpUrl("https://example.com/test.jpg")
    route = respx.get(str(url))

    # Fail twice, then succeed
    route.side_effect = [
        httpx.RequestError("Connection failed"),
        httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=MagicMock(status_code=500)),
        httpx.Response(200, content=b"success"),
    ]

    result = await vk_manager.download_file(url, tmp_path)

    assert result is not None
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_async_with_support(settings: Settings):
    manager = VKManager()
    with patch.object(manager, "shutdown", new_callable=AsyncMock) as mock_shutdown:
        async with manager as mgr:
            await mgr.setup(settings)
            assert mgr is manager
            assert mgr._initialized  # type: ignore[reportPrivateUsage]
        mock_shutdown.assert_awaited_once()
