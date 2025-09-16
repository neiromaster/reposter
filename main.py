import asyncio

from reposter.__main__ import main
from reposter.core.composition import DefaultAppComposer

if __name__ == "__main__":
    composer = DefaultAppComposer()
    asyncio.run(main(composer))
