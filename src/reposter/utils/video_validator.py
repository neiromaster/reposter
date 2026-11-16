from __future__ import annotations

import asyncio
import contextlib
import json
import shutil

# Subprocess entry point; patched by tests and consumed by the decode pass.
from asyncio import create_subprocess_exec
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard, cast

from .log import log

# Timeout for the full-decode pass: floor + scaling per second of media, so long
# videos on weak CPUs are not falsely invalidated by a fixed cap.
MIN_TIMEOUT_SECONDS = 600
TIMEOUT_PER_MEDIA_SECOND = 8
PROBE_TIMEOUT_SECONDS = 30.0
# Tolerance when comparing durations: max(2s, 1% of the larger duration).
DURATION_TOLERANCE_SECONDS = 2.0
DURATION_TOLERANCE_RATIO = 0.01

# Matched casefold against ffmpeg stderr — message casing/wording drifts between versions.
FATAL_DECODE_PATTERNS = (
    "invalid data found when processing input",
    "error splitting the input into nal units",
    "moov atom not found",
    "error while decoding stream",
    "error while decoding mb",
    "decoding error",
    "error submitting packet to decoder",
)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a downloaded video file."""

    valid: bool
    skipped: bool
    reason: str


def _ok() -> ValidationResult:
    return ValidationResult(valid=True, skipped=False, reason="ok")


def _invalid(reason: str) -> ValidationResult:
    return ValidationResult(valid=False, skipped=False, reason=reason)


def _fail_open(reason: str) -> ValidationResult:
    return ValidationResult(valid=True, skipped=True, reason=reason)


async def _run_command(program: str, args: list[str]) -> tuple[int, bytes, bytes]:
    """Runs a subprocess, returns (returncode, stdout, stderr). Kills the child when cancelled."""
    proc = await create_subprocess_exec(
        program,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await proc.communicate()
    except BaseException:
        # kill() itself can raise (Windows PermissionError on an exited-but-undrained child,
        # POSIX ProcessLookupError after an external reap); that must not mask the CancelledError.
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(BaseException):
            await proc.wait()
        raise
    returncode = proc.returncode if proc.returncode is not None else -1
    return returncode, stdout, stderr


async def _probe_media(path: Path) -> dict[str, Any] | None:
    """Runs ffprobe and returns parsed JSON, or None when probing is unavailable."""
    args = [
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,duration",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            returncode, stdout, _stderr = await _run_command("ffprobe", args)
    except (TimeoutError, OSError):
        return None
    if returncode != 0:
        return None
    try:
        return cast(dict[str, Any], json.loads(stdout.decode("utf-8", errors="replace")))
    except json.JSONDecodeError:
        return None


def _parse_duration(value: Any) -> float | None:
    """Parses an ffprobe duration (string or number) into seconds."""
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _is_stream_entry(item: Any) -> TypeGuard[dict[str, Any]]:
    """Narrows a probe stream item to a JSON object; guards against malformed probe output."""
    return isinstance(item, dict)


def _duration_tolerance(*durations: float | None) -> float:
    """max(2s, 1% of the largest known duration)."""
    known = [d for d in durations if d is not None]
    reference = max(known) if known else 0.0
    return max(DURATION_TOLERANCE_SECONDS, reference * DURATION_TOLERANCE_RATIO)


def _stream_duration_mismatch(probe: dict[str, Any] | None) -> str | None:
    """Returns an invalid-reason when video and audio stream durations diverge beyond tolerance."""
    if not probe:
        return None
    streams = probe.get("streams")
    if not isinstance(streams, list):
        return None
    durations = {
        s.get("codec_type"): _parse_duration(s.get("duration")) for s in cast(list[Any], streams) if _is_stream_entry(s)
    }
    video = durations.get("video")
    audio = durations.get("audio")
    if video is None or audio is None:
        return None
    tolerance = _duration_tolerance(video, audio)
    if abs(video - audio) > tolerance:
        return f"длительности потоков расходятся: видео {video:.1f}с против аудио {audio:.1f}с"
    return None


def _has_fatal_decode_error(stderr_text: str) -> str | None:
    """Returns the first fatal decode pattern found in casefolded ffmpeg stderr."""
    folded = stderr_text.casefold()
    for pattern in FATAL_DECODE_PATTERNS:
        if pattern in folded:
            return pattern
    return None


def _parse_decoded_seconds(progress_text: str) -> float | None:
    """Extracts the last out_time (seconds) from ffmpeg -progress output.

    ffmpeg reports both `out_time_us` and `out_time_ms`; despite the `ms` name
    both carry microseconds.
    """
    seconds: float | None = None
    for line in progress_text.splitlines():
        key, _, raw = line.partition("=")
        if key not in ("out_time_us", "out_time_ms"):
            continue
        try:
            seconds = float(raw.strip()) / 1_000_000
        except ValueError:
            continue
    return seconds


def _container_duration(probe: dict[str, Any] | None) -> float | None:
    """Container duration in seconds from ffprobe output."""
    if not probe:
        return None
    fmt = probe.get("format")
    if not isinstance(fmt, dict):
        return None
    return _parse_duration(cast(dict[str, Any], fmt).get("duration"))


async def _decode_check(path: Path, timeout_seconds: float) -> tuple[int, bytes, bytes]:
    """Runs the full-decode ffmpeg pass; returns (returncode, stdout, stderr).

    stdout carries `-progress pipe:1` telemetry, stderr carries `-v error` messages.
    Kills the child on timeout via _run_command's cancellation path.
    """
    args = [
        "-v",
        "error",
        "-nostdin",
        "-nostats",
        "-progress",
        "pipe:1",
        "-i",
        str(path),
        "-f",
        "null",
        "-",
    ]
    async with asyncio.timeout(timeout_seconds):
        return await _run_command("ffmpeg", args)


async def validate_video_file(path: Path, *, timeout_seconds: float | None = None) -> ValidationResult:
    """Validates a downloaded video: stream sanity and full-decode completeness.

    `timeout_seconds` overrides the derived decode timeout (used by tests).
    """
    if not path.exists() or path.stat().st_size == 0:
        return _invalid("файл не существует или пуст")

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        log("⚠️ ffmpeg/ffprobe не найдены в PATH — проверка целостности видео пропущена.", indent=4)
        return _fail_open("ffmpeg/ffprobe не найдены — проверка пропущена")

    probe = await _probe_media(path)
    mismatch = _stream_duration_mismatch(probe)
    if mismatch:
        return _invalid(mismatch)

    container = _container_duration(probe)
    if timeout_seconds is not None:
        timeout = float(timeout_seconds)
    else:
        timeout = max(float(MIN_TIMEOUT_SECONDS), container * TIMEOUT_PER_MEDIA_SECOND if container else 0.0)
    try:
        returncode, stdout, stderr = await _decode_check(path, timeout)
    except TimeoutError:
        return _invalid(f"декодирование превысило таймаут {timeout:.0f} сек")
    except OSError:
        return _fail_open("ffmpeg не удалось запустить")

    fatal = _has_fatal_decode_error(stderr.decode("utf-8", errors="replace"))
    if fatal:
        return _invalid(f"ошибка декодирования: {fatal}")
    if returncode != 0:
        return _invalid(f"ffmpeg завершился с кодом {returncode}")

    progress_text = stdout.decode("utf-8", errors="replace")
    if "progress=end" not in progress_text:
        return _invalid("декодирование не завершилось (нет progress=end)")
    decoded = _parse_decoded_seconds(progress_text)
    if container is not None and decoded is not None:
        tolerance = _duration_tolerance(container, decoded)
        if abs(container - decoded) > tolerance:
            if decoded > container:
                return _invalid(
                    f"декодирование расходится с контейнером: декодировано {decoded:.1f}с из {container:.1f}с"
                )
            return _invalid(f"поток усечён: декодировано {decoded:.1f}с из {container:.1f}с")

    return _ok()
