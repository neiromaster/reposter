from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.utils.video_validator import validate_video_file


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:  # type: ignore[reportUnusedFunction]
    """Builds a fake asyncio subprocess with a completed communicate()."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_missing_file_invalid(tmp_path: Path):
    """A nonexistent file is invalid without launching any subprocess."""
    with patch("src.reposter.utils.video_validator.create_subprocess_exec") as mock_exec:
        result = await validate_video_file(tmp_path / "missing.mp4")
    assert result.valid is False
    assert result.skipped is False
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_empty_file_invalid(tmp_path: Path):
    """A zero-byte file is invalid without launching any subprocess."""
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with patch("src.reposter.utils.video_validator.create_subprocess_exec") as mock_exec:
        result = await validate_video_file(empty)
    assert result.valid is False
    assert result.skipped is False
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_missing_binaries_fail_open(tmp_path: Path):
    """Without ffmpeg/ffprobe in PATH validation is skipped (fail-open)."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value=None),
        patch("src.reposter.utils.video_validator.create_subprocess_exec") as mock_exec,
    ):
        result = await validate_video_file(video)
    assert result.valid is True
    assert result.skipped is True
    mock_exec.assert_not_called()
