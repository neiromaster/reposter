from abc import ABC, abstractmethod


class BaseAppManager(ABC):
    @abstractmethod
    async def run(self) -> None:
        pass
