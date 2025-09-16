from abc import ABC, abstractmethod
from asyncio import Event
from types import TracebackType

from ..config.settings import Settings


class BaseManager(ABC):
    """
    Base interface for all managers.
    Any manager must implement these methods.
    """

    @abstractmethod
    def set_shutdown_event(self, event: Event) -> None:
        """Called once on application startup to set the shutdown event."""
        pass

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
