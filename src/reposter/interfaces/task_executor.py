from abc import ABC, abstractmethod
from asyncio import Event

from ..config.settings import Settings


class BaseTaskExecutor(ABC):
    """
    Interface for the main task executor.
    Encapsulates all business logic.
    """

    @abstractmethod
    async def execute(self, settings: Settings) -> None:
        """Executes the main task of the application."""
        pass

    @abstractmethod
    def set_shutdown_event(self, event: Event) -> None:
        """Sets the shutdown event."""
        pass
