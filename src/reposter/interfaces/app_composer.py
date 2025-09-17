from abc import ABC, abstractmethod

from ..interfaces.app_manager import BaseAppManager


class AppComposer(ABC):
    @abstractmethod
    def compose_app(self, debug: bool = False) -> BaseAppManager:
        pass
