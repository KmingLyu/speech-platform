import json
import os
import shutil
from pathlib import Path
from uuid import uuid4


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def _write_text_durably(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def export_result(job_id: str, *, output_dir: Path, text: str, language: str | None,
                  duration: float, model: str,
                  segments: list[dict], formats: tuple[str, ...],
                  job_type: str = "transcription", metadata: dict | None = None) -> dict[str, Path]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir.with_name(f".{output_dir.name}.staging-{uuid4().hex}")
    try:
        staging_dir.mkdir()
        paths: dict[str, Path] = {}
        json_path = staging_dir / "result.json"
        if "json" in formats:
            _write_text_durably(json_path, json.dumps({
                "schema_version": "1.0", "artifact_type": "diarized_transcript" if job_type == "diarization" else "transcript",
                "job_id": job_id, "language": language,
                "duration": duration, "text": text, "segments": segments,
                "metadata": {
                    "provider": "faster-whisper", "model": model,
                    **(metadata or {}),
                },
            }, ensure_ascii=False, indent=2))
            paths["json"] = output_dir / json_path.name
        if "txt" in formats:
            txt_path = staging_dir / "transcript.txt"
            lines = [
                f"[{segment.get('speaker') or 'UNKNOWN'}] {segment['text']}" if job_type == "diarization" else segment["text"]
                for segment in segments
            ]
            _write_text_durably(txt_path, ("\n".join(lines) if job_type == "diarization" else text) + "\n")
            paths["txt"] = output_dir / txt_path.name
        if "srt" in formats:
            srt_path = staging_dir / "transcript.srt"
            def line(segment: dict) -> str:
                speaker = f"[{segment.get('speaker') or 'UNKNOWN'}] " if job_type == "diarization" else ""
                return f"{segment['id'] + 1}\n{srt_timestamp(segment['start'])} --> {srt_timestamp(segment['end'])}\n{speaker}{segment['text']}\n"
            _write_text_durably(srt_path, "\n".join(
                line(segment)
                for segment in segments
            ))
            paths["srt"] = output_dir / srt_path.name

        if output_dir.exists():
            shutil.rmtree(output_dir)
        staging_dir.replace(output_dir)
        directory_fd = os.open(output_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        parent_fd = os.open(output_dir.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return paths
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
