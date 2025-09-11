from abc import ABC, abstractmethod

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
