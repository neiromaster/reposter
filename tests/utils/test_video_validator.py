# pyright: reportPrivateUsage=false
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reposter.utils.video_validator import (
    ValidationResult,
    _run_command,
    _stream_duration_mismatch,
    validate_video_file,
)


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


DECODE_OK_STDOUT = b"progress=continue\nout_time_us=20000000\nprogress=end\n"


@pytest.mark.asyncio
async def test_healthy_video_valid(tmp_path: Path):
    """rc=0, empty stderr, decoded duration == container duration, progress=end -> valid."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(returncode=0, stdout=DECODE_OK_STDOUT, stderr=b"")
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result == ValidationResult(valid=True, skipped=False, reason="ok")


@pytest.mark.asyncio
async def test_fatal_decode_pattern_any_case(tmp_path: Path):
    """A fatal pattern matches case-insensitively."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(
        returncode=0,
        stdout=DECODE_OK_STDOUT,
        stderr=b"Error splitting the input into NAL units.\n",
    )
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is False
    assert "nal units" in result.reason


@pytest.mark.asyncio
async def test_benign_stderr_noise_still_valid(tmp_path: Path):
    """stderr lines outside the pattern list do not invalidate the file."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(
        returncode=0,
        stdout=DECODE_OK_STDOUT,
        stderr=b"some unrelated decoder chatter\n",
    )
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is True


@pytest.mark.asyncio
async def test_nonzero_returncode_invalid(tmp_path: Path):
    """ffmpeg exiting non-zero invalidates the file even with empty stderr."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(returncode=183, stdout=b"", stderr=b"")
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is False
    assert "183" in result.reason


@pytest.mark.asyncio
async def test_probe_failure_skips_precheck_but_still_decodes(tmp_path: Path):
    """ffprobe failing (rc!=0) skips the pre-check; the decode pass still decides."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=1, stdout=b"")
    decode_proc = _make_proc(returncode=0, stdout=DECODE_OK_STDOUT, stderr=b"")
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result == ValidationResult(valid=True, skipped=False, reason="ok")


@pytest.mark.asyncio
async def test_malformed_probe_json_skips_precheck_but_still_decodes(tmp_path: Path):
    """Non-JSON ffprobe stdout skips the pre-check; the decode pass still decides."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=b"not json")
    decode_proc = _make_proc(returncode=0, stdout=DECODE_OK_STDOUT, stderr=b"")
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result == ValidationResult(valid=True, skipped=False, reason="ok")


async def _communicate_hang() -> tuple[bytes, bytes]:
    """Stands in for communicate() on a child that never finishes; only cancellation ends it."""
    await asyncio.sleep(10)
    raise AssertionError("communicate was not cancelled by the timeout")


@pytest.mark.asyncio
async def test_run_command_kills_child_on_timeout():
    """_run_command kills and reaps the child when the caller's asyncio.timeout expires."""
    slow_proc = _make_proc(returncode=0)
    slow_proc.communicate = AsyncMock(side_effect=_communicate_hang)
    with (
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(return_value=slow_proc),
        ),
        pytest.raises(TimeoutError),
    ):
        async with asyncio.timeout(0.05):
            await _run_command("ffmpeg", ["-version"])
    slow_proc.kill.assert_called_once()
    slow_proc.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_truncated_stream_detected_by_progress(tmp_path: Path):
    """Silent truncation: rc=0, empty stderr, but decoded 12.7s of a 20.0s container."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(
        returncode=0,
        stdout=b"progress=continue\nout_time_us=12701000\nprogress=end\n",
        stderr=b"",
    )
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is False
    assert "усечён" in result.reason


@pytest.mark.asyncio
async def test_missing_progress_end_invalid(tmp_path: Path):
    """A decode pass that never reports progress=end is invalid."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(returncode=0, stdout=b"progress=continue\nout_time_us=20000000\n", stderr=b"")
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is False
    assert "progress=end" in result.reason


@pytest.mark.asyncio
async def test_timeout_kills_process_and_invalid(tmp_path: Path):
    """Decode timeout: process is killed (no leak) and the file is invalid."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    hang_proc = _make_proc(returncode=0)
    hang_proc.communicate = AsyncMock(side_effect=_communicate_hang)
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, hang_proc]),
        ),
    ):
        result = await validate_video_file(video, timeout_seconds=0.05)
    assert result.valid is False
    assert "таймаут" in result.reason
    hang_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_fatal_pattern_wins_over_returncode(tmp_path: Path):
    """When both a fatal pattern and a nonzero rc are present, the pattern is reported."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    probe_proc = _make_proc(returncode=0, stdout=_probe_json("20.0", "20.0", "20.0"))
    decode_proc = _make_proc(
        returncode=1,
        stdout=DECODE_OK_STDOUT,
        stderr=b"Error splitting the input into NAL units.\n",
    )
    with (
        patch("src.reposter.utils.video_validator.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "src.reposter.utils.video_validator.create_subprocess_exec",
            new=AsyncMock(side_effect=[probe_proc, decode_proc]),
        ),
    ):
        result = await validate_video_file(video)
    assert result.valid is False
    assert "nal units" in result.reason
    assert "завершился" not in result.reason
