import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from .failures import ClassifiedFailure, PermanentFailure, RetryableFailure


class MediaError(PermanentFailure):
    """The media cannot be probed or decoded, so another Attempt cannot help."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            "media_unreadable",
            "The media could not be decoded.",
            detail=reason,
        )


class MediaProcessingError(RetryableFailure):
    """Transcoding failed for a reason that may be environmental, such as disk,
    memory, or tooling, so another Attempt may succeed."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            "media_processing_failed",
            "The media could not be processed.",
            detail=reason,
        )


def run(
    command: list[str],
    failure: Callable[[str], ClassifiedFailure],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown command failure"
        raise failure(message)
    return result


def probe_duration(source_path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(source_path),
    ], MediaError)
    payload = json.loads(result.stdout)
    duration = payload.get("format", {}).get("duration")
    if duration is None:
        raise MediaError("Media duration is unavailable")
    return float(duration)


def normalize_audio(source_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(source_path), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "flac", str(output_path),
    ], MediaProcessingError)
    return output_path
