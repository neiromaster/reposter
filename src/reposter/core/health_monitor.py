from collections.abc import Awaitable, Callable
from typing import Any


class HealthMonitor:
    def __init__(self) -> None:
        self.checks: dict[str, Callable[[], Awaitable[Any]]] = {}

    def register_check(self, name: str, check_func: Callable[[], Awaitable[Any]]) -> None:
        self.checks[name] = check_func

    async def check_health(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, check_func in self.checks.items():
            try:
                results[name] = await check_func()
            except Exception as e:
                results[name] = {"status": "error", "message": str(e)}
        return results
