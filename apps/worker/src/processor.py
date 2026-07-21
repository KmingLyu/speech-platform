from pathlib import Path

from .config import Settings
from .exporter import export_result
from .media import normalize_audio, probe_duration
from .repository import complete_job, fail_job, update_job
from .script_converter import convert_segments, convert_text
from .source import acquire_source
from .transcriber import Transcriber


def process_job(settings: Settings, transcriber: Transcriber, job: dict) -> None:
    job_id = job["id"]
    job_root = settings.data_root / "jobs" / job_id
    try:
        update_job(settings, job_id, status="acquiring_source", progress=2, current_stage="acquiring_source")
        source_path = acquire_source(job, job_root)

        update_job(settings, job_id, status="probing", progress=5, current_stage="probing")
        duration = probe_duration(source_path)
        update_job(settings, job_id, duration=duration)

        update_job(settings, job_id, status="transcoding", progress=10, current_stage="transcoding")
        audio_path = normalize_audio(source_path, job_root / "work" / "audio.flac")

        update_job(settings, job_id, status="transcribing", progress=15, current_stage="transcribing")
        text, segments = transcriber.transcribe(
            audio_path, model_name=job["model"], language=job["language"],
        )
        output_script = job.get("output_script", "original")
        text = convert_text(text, output_script)
        segments = convert_segments(segments, output_script)
        update_job(settings, job_id, progress=90, processed_seconds=duration)

        update_job(settings, job_id, status="exporting", progress=95, current_stage="exporting")
        json_path, txt_path, srt_path = export_result(
            job_id, output_dir=job_root / "result", text=text, language=job["language"],
            duration=duration, model=job["model"], output_script=output_script,
            segments=segments,
        )
        complete_job(settings, job_id, text=text, json_path=str(json_path),
                     txt_path=str(txt_path), srt_path=str(srt_path))
        audio_path.unlink(missing_ok=True)
    except Exception as error:
        fail_job(settings, job_id, "processing_failed", str(error))
