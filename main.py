import asyncio
import multiprocessing
import sys
from pathlib import Path

# Add the src directory to the Python path
# This is necessary for the executable created by PyInstaller to find the reposter module
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from reposter.__main__ import main  # noqa: E402
from reposter.core.composition import DefaultAppComposer  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    composer = DefaultAppComposer()
    asyncio.run(main(composer))
