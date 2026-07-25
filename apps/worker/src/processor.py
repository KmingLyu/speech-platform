import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings


logger = logging.getLogger(__name__)


class JobLifecycle(Protocol):
    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        current_stage: str | None = None,
        duration: float | None = None,
        processed_seconds: float | None = None,
    ) -> None: ...

    def complete(
        self,
        job_id: str,
        *,
        text: str,
        artifacts: dict[str, str],
    ) -> None: ...

    def fail(self, job_id: str, code: str, message: str) -> None: ...


class SourceAcquirer(Protocol):
    def acquire(self, job: dict, job_root: Path) -> Path: ...


class MediaProcessor(Protocol):
    def probe_duration(self, source_path: Path) -> float: ...

    def normalize_audio(self, source_path: Path, output_path: Path) -> Path: ...


class TranscriptionEngine(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        language: str | None,
    ) -> tuple[str, list[dict]]: ...


class TranscriptConverter(Protocol):
    def convert(
        self,
        text: str,
        segments: list[dict],
        output_script: str,
    ) -> tuple[str, list[dict]]: ...


class ArtifactWriter(Protocol):
    def write(
        self,
        job_id: str,
        *,
        output_dir: Path,
        text: str,
        language: str | None,
        duration: float,
        model: str,
        output_script: str,
        segments: list[dict],
        formats: tuple[str, ...],
    ) -> dict[str, Path]: ...


@dataclass(frozen=True)
class WorkerDependencies:
    jobs: JobLifecycle
    sources: SourceAcquirer
    media: MediaProcessor
    transcription: TranscriptionEngine
    converter: TranscriptConverter
    artifacts: ArtifactWriter


def process_job(
    settings: Settings,
    dependencies: WorkerDependencies,
    job: dict,
) -> None:
    job_id = job["id"]
    job_root = settings.data_root / "jobs" / job_id
    try:
        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=2,
            current_stage="acquiring_source",
        )
        source_path = dependencies.sources.acquire(job, job_root)

        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=5,
            current_stage="probing",
        )
        duration = dependencies.media.probe_duration(source_path)
        dependencies.jobs.update(job_id, duration=duration)

        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=10,
            current_stage="transcoding",
        )
        audio_path = dependencies.media.normalize_audio(
            source_path,
            job_root / "work" / "audio.flac",
        )

        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=15,
            current_stage="transcribing",
        )
        text, segments = dependencies.transcription.transcribe(
            audio_path, model_name=job["model"], language=job["language"],
        )
        output_script = job.get("output_script", "original")
        text, segments = dependencies.converter.convert(
            text,
            segments,
            output_script,
        )
        dependencies.jobs.update(
            job_id,
            progress=90,
            processed_seconds=duration,
        )

        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=95,
            current_stage="exporting",
        )
        artifacts = dependencies.artifacts.write(
            job_id, output_dir=job_root / "result", text=text, language=job["language"],
            duration=duration, model=job["model"], output_script=output_script,
            segments=segments, formats=tuple(job.get("output_formats", ("json", "txt", "srt"))),
        )
        dependencies.jobs.complete(
            job_id,
            text=text,
            artifacts={format: str(path) for format, path in artifacts.items()},
        )
        audio_path.unlink(missing_ok=True)
    except Exception:
        logger.exception("transcription job %s failed", job_id)
        dependencies.jobs.fail(job_id, "processing_failed", "Transcription processing failed.")
