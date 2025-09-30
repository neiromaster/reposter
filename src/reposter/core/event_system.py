"""Event system module for the application."""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from typing import Any, TypeVar

from ..utils.log import log


class Event:
    """Base class for all events."""

    def __init__(self, name: str, data: dict[str, Any] | None = None) -> None:
        self.name = name
        self.data = data or {}
        self.timestamp = asyncio.get_event_loop().time()


class AppStartEvent(Event):
    """Event emitted when the application starts."""

    def __init__(self) -> None:
        super().__init__("APP_START")


class AppStopEvent(Event):
    """Event emitted when the application stops."""

    def __init__(self) -> None:
        super().__init__("APP_STOP")


class TaskExecutionRequestEvent(Event):
    """Event emitted when a task execution is requested."""

    def __init__(self, force: bool = False) -> None:
        super().__init__("TASK_EXECUTION_REQUEST", {"force": force})


class TaskExecutionCompleteEvent(Event):
    """Event emitted when a task execution is completed."""

    def __init__(self, success: bool = True, error: str | None = None) -> None:
        super().__init__("TASK_EXECUTION_COMPLETE", {"success": success, "error": error})


class HealthCheckRequestEvent(Event):
    """Event emitted when a health check is requested."""

    def __init__(self) -> None:
        super().__init__("HEALTH_CHECK_REQUEST")


class UserInputReceivedEvent(Event):
    """Event emitted when user input is received."""

    def __init__(self, command: str) -> None:
        super().__init__("USER_INPUT_RECEIVED", {"command": command})


class PeriodicTaskScheduledEvent(Event):
    """Event emitted when a periodic task is scheduled."""

    def __init__(self, delay: float) -> None:
        super().__init__("PERIODIC_TASK_SCHEDULED", {"delay": delay})


T = TypeVar("T", bound=Event)


class EventManager:
    """Manages event subscription and dispatch."""

    def __init__(self) -> None:
        self._handlers: defaultdict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._async_handlers: defaultdict[str, list[Callable[[Event], Any]]] = defaultdict(list)
        self._running = True

    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> None:
        """Subscribe to an event.

        Automatically detects if the handler is async or not.
        """
        if asyncio.iscoroutinefunction(handler):
            self._async_handlers[event_name].append(handler)
        else:
            self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable[[Event], Any]) -> None:
        """Unsubscribe from an event."""
        if event_name in self._handlers:
            with suppress(ValueError):
                self._handlers[event_name].remove(handler)

        if event_name in self._async_handlers:
            with suppress(ValueError):
                self._async_handlers[event_name].remove(handler)

    async def emit(self, event: Event) -> None:
        """Emit an event to all subscribed handlers."""
        if not self._running:
            return

        # Execute sync handlers first
        for handler in self._handlers.get(event.name, []):
            try:
                handler(event)
            except Exception as e:
                log(f"❌ Error in sync handler for event {event.name}: {e}")

        # Then execute async handlers
        tasks: list[Any] = []
        for handler in self._async_handlers.get(event.name, []):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    tasks.append(result)
            except Exception as e:
                log(f"❌ Error in async handler for event {event.name}: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self) -> None:
        """Stop the event manager."""
        self._running = False
