import asyncio
from contextlib import suppress

from src.reposter.manager import AppManager

if __name__ == "__main__":
    manager = AppManager(period=10)
    with suppress(KeyboardInterrupt):
        asyncio.run(manager.run())
