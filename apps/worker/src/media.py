import json
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown command failure"
        raise MediaError(message)
    return result


def probe_duration(source_path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(source_path),
    ])
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
    ])
    return output_path
