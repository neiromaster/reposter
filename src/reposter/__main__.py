import argparse
import asyncio
import sys
from pathlib import Path

from .core.composition import DefaultAppComposer
from .interfaces.app_composer import AppComposer
from .utils.log import log


async def main(composer: AppComposer):
    parser = argparse.ArgumentParser(description="VK to Telegram Reposter.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode.")
    args = parser.parse_args()

    try:
        if not Path("config.yaml").exists():
            raise FileNotFoundError("config.yaml не найден")

        app = composer.compose_app(debug=args.debug)
        await app.run()

    except Exception as e:
        log(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    composer = DefaultAppComposer()
    asyncio.run(main(composer))
