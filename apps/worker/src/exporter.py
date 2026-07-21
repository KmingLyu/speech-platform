import json
from pathlib import Path


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def export_result(job_id: str, *, output_dir: Path, text: str, language: str | None,
                  duration: float, model: str, output_script: str,
                  segments: list[dict]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "result.json"
    txt_path = output_dir / "transcript.txt"
    srt_path = output_dir / "transcript.srt"
    json_path.write_text(json.dumps({
        "schema_version": "1.0", "job_id": job_id, "language": language,
        "duration": duration, "text": text, "segments": segments,
        "metadata": {
            "provider": "faster-whisper", "model": model,
            "output_script": output_script,
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(text + "\n", encoding="utf-8")
    srt_path.write_text("\n".join(
        f"{segment['id'] + 1}\n{srt_timestamp(segment['start'])} --> {srt_timestamp(segment['end'])}\n{segment['text']}\n"
        for segment in segments
    ), encoding="utf-8")
    return json_path, txt_path, srt_path
