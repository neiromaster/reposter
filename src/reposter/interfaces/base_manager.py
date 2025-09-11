from abc import ABC, abstractmethod

from ..config.settings import Settings


class BaseManager(ABC):
    """
    Base interface for all managers.
    Any manager must implement these methods.
    """

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
