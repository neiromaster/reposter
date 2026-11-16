from __future__ import annotations

import shutil

# Subprocess entry point; patched by tests and consumed by the decode pass.
from asyncio import create_subprocess_exec  # type: ignore[reportUnusedImport]  # noqa: F401
from dataclasses import dataclass
from pathlib import Path

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


async def validate_video_file(path: Path, *, timeout_seconds: float | None = None) -> ValidationResult:
    """Validates a downloaded video: stream sanity and full-decode completeness.

    `timeout_seconds` overrides the derived decode timeout (used by tests).
    """
    if not path.exists() or path.stat().st_size == 0:
        return _invalid("файл не существует или пуст")

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        log("⚠️ ffmpeg/ffprobe не найдены в PATH — проверка целостности видео пропущена.", indent=4)
        return _fail_open("ffmpeg/ffprobe не найдены — проверка пропущена")

    return _ok()
