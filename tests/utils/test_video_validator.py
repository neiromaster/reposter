# pyright: reportPrivateUsage=false
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.utils.video_validator import _stream_duration_mismatch, validate_video_file


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
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


def _probe_json(video: str, audio: str, container: str) -> bytes:
    return json.dumps(
        {
            "streams": [
                {"codec_type": "video", "duration": video},
                {"codec_type": "audio", "duration": audio},
            ],
            "format": {"duration": container},
        }
    ).encode()


def test_stream_duration_mismatch_detected():
    probe = {"streams": [{"codec_type": "video", "duration": "10.0"}, {"codec_type": "audio", "duration": "20.0"}]}
    reason = _stream_duration_mismatch(probe)
    assert reason is not None
    assert "10.0" in reason and "20.0" in reason


def test_stream_duration_match_passes():
    probe = {"streams": [{"codec_type": "video", "duration": "20.0"}, {"codec_type": "audio", "duration": "20.0"}]}
    assert _stream_duration_mismatch(probe) is None


def test_stream_check_skipped_when_no_audio_stream():
    probe = {"streams": [{"codec_type": "video", "duration": "20.0"}]}
    assert _stream_duration_mismatch(probe) is None


def test_stream_check_skipped_when_probe_failed():
    assert _stream_duration_mismatch(None) is None


@pytest.mark.asyncio
async def test_short_video_stream_invalid_before_decode(tmp_path: Path):
    """10s video vs 20s audio is invalid; the mismatch is reported."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("10.0", "20.0", "20.0"))
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(return_value=probe_proc),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is False
    assert result.skipped is False
    assert "потоков" in result.reason
