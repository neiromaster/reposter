from unittest.mock import AsyncMock, MagicMock

import pytest

from src.reposter.core.event_system import Event, EventManager


@pytest.fixture
def event_manager() -> EventManager:
    """Fixture for creating an EventManager instance."""
    return EventManager()


@pytest.mark.asyncio
async def test_subscribe_and_emit(event_manager: EventManager):
    """Test that a handler is called when an event is emitted."""
    # Arrange
    sync_handler = MagicMock()
    async_handler = AsyncMock()
    event = Event("TEST_EVENT")

    event_manager.subscribe("TEST_EVENT", sync_handler)
    event_manager.subscribe("TEST_EVENT", async_handler)

    # Act
    await event_manager.emit(event)

    # Assert
    sync_handler.assert_called_once_with(event)
    async_handler.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_unsubscribe(event_manager: EventManager):
    """Test that a handler is not called after unsubscribing."""
    # Arrange
    handler = MagicMock()
    event = Event("TEST_EVENT")

    event_manager.subscribe("TEST_EVENT", handler)
    event_manager.unsubscribe("TEST_EVENT", handler)

    # Act
    await event_manager.emit(event)

    # Assert
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_emit_with_no_handlers(event_manager: EventManager):
    """Test that emitting an event with no handlers does not raise an error."""
    # Arrange
    event = Event("TEST_EVENT")

    # Act & Assert
    try:
        await event_manager.emit(event)
    except Exception as e:
        pytest.fail(f"emit() raised an exception with no handlers: {e}")


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_others(event_manager: EventManager):
    """Test that an exception in one handler does not stop others from running."""
    # Arrange
    failing_sync_handler = MagicMock(side_effect=Exception("Sync error"))
    working_sync_handler = MagicMock()
    failing_async_handler = AsyncMock(side_effect=Exception("Async error"))
    working_async_handler = AsyncMock()

    event = Event("TEST_EVENT")

    event_manager.subscribe("TEST_EVENT", failing_sync_handler)
    event_manager.subscribe("TEST_EVENT", working_sync_handler)
    event_manager.subscribe("TEST_EVENT", failing_async_handler)
    event_manager.subscribe("TEST_EVENT", working_async_handler)

    # Act
    await event_manager.emit(event)

    # Assert
    failing_sync_handler.assert_called_once()
    working_sync_handler.assert_called_once()
    failing_async_handler.assert_awaited_once()
    working_async_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_prevents_emit(event_manager: EventManager):
    """Test that emitting an event after stopping does nothing."""
    # Arrange
    handler = MagicMock()
    event = Event("TEST_EVENT")
    event_manager.subscribe("TEST_EVENT", handler)

    # Act
    event_manager.stop()
    await event_manager.emit(event)

    # Assert
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_unsubscribe_from_non_existent_handler(event_manager: EventManager):
    """Test that unsubscribing a non-existent handler does not raise an error."""
    # Arrange
    handler = MagicMock()

    # Act & Assert
    try:
        event_manager.unsubscribe("TEST_EVENT", handler)
    except Exception as e:
        pytest.fail(f"unsubscribe() raised an exception for a non-existent handler: {e}")
