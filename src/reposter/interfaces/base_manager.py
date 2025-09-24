from abc import ABC, abstractmethod
from asyncio import CancelledError, Event
from types import TracebackType

from ..config.settings import Settings


class BaseManager(ABC):
    """
    Base interface for all managers.
    Any manager must implement these methods.
    """

    def __init__(self) -> None:
        self._shutdown_event: Event | None = None

    def set_shutdown_event(self, event: Event) -> None:
        """Called once on application startup to set the shutdown event."""
        self._shutdown_event = event

    def _check_shutdown(self) -> None:
        """Check if shutdown event is set and raise CancelledError if so."""
        if self._shutdown_event and self._shutdown_event.is_set():
            raise CancelledError("Shutdown requested")

    @abstractmethod
    async def setup(self, settings: Settings) -> None:
        """Called once on application startup."""
        pass

    @abstractmethod
    async def update_config(self, settings: Settings) -> None:
        """Called when the configuration changes."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Called on application shutdown."""
        pass

    @abstractmethod
    async def __aenter__(self) -> "BaseManager":
        """Enter the async context manager."""
        pass

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and shutdown the client."""
        pass
