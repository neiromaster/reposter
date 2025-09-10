import asyncio
from contextlib import suppress

from .core.manager import AppManager


def main():
    """Main entry point for the application script"""
    manager = AppManager(period=30)
    with suppress(KeyboardInterrupt):
        asyncio.run(manager.run())


if __name__ == "__main__":
    main()
