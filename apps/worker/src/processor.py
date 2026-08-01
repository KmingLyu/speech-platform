import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings
from .failures import alignment_failed, classify_failure, empty_transcript, no_speakers_detected
from .alignment import AlignmentEngine, AlignmentResult, AlignmentUnavailable
from .attribution import attribute_words
from .diarizer import DiarizationEngine
from .display_segments import display_segments


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

    def fail(self, job_id: str, code: str, message: str, *, retryable: bool) -> None: ...

    def cancel_if_requested(self, job_id: str) -> bool: ...

    def heartbeat(self, job_id: str) -> None: ...


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
        job_type: str = "transcription",
        metadata: dict | None = None,
    ) -> dict[str, Path]: ...

    def discard(self, output_dir: Path) -> None: ...


@dataclass(frozen=True)
class WorkerDependencies:
    jobs: JobLifecycle
    sources: SourceAcquirer
    media: MediaProcessor
    transcription: TranscriptionEngine
    converter: TranscriptConverter
    artifacts: ArtifactWriter
    alignment: AlignmentEngine | None = None
    diarization: DiarizationEngine | None = None


def _stop_if_canceled(
    dependencies: WorkerDependencies,
    job_id: str,
    job_root: Path,
    audio_path: Path | None,
) -> bool:
    """Confirm cancellation at a safe checkpoint, discarding any partial Attempt."""
    if not dependencies.jobs.cancel_if_requested(job_id):
        return False
    if audio_path is not None:
        audio_path.unlink(missing_ok=True)
    discard = getattr(dependencies.artifacts, "discard", None)
    if discard is not None:
        discard(job_root / "result")
    return True


def process_job(
    settings: Settings,
    dependencies: WorkerDependencies,
    job: dict,
) -> None:
    job_id = job["id"]
    job_root = settings.data_root / "jobs" / job_id
    audio_path: Path | None = None
    stop_heartbeat = threading.Event()

    def refresh_heartbeat() -> None:
        while not stop_heartbeat.wait(settings.heartbeat_interval_seconds):
            try:
                dependencies.jobs.heartbeat(job_id)
            except Exception:
                logger.exception("failed to refresh heartbeat for job %s", job_id)

    heartbeat_method = getattr(dependencies.jobs, "heartbeat", None)
    heartbeat_thread = threading.Thread(target=refresh_heartbeat, daemon=True)
    if heartbeat_method is not None:
        heartbeat_thread.start()
    try:
        if _stop_if_canceled(dependencies, job_id, job_root, audio_path):
            return
        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=2,
            current_stage="acquiring_source",
        )
        source_path = dependencies.sources.acquire(job, job_root)

        if _stop_if_canceled(dependencies, job_id, job_root, audio_path):
            return
        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=5,
            current_stage="probing",
        )
        duration = dependencies.media.probe_duration(source_path)
        dependencies.jobs.update(job_id, duration=duration)

        if _stop_if_canceled(dependencies, job_id, job_root, audio_path):
            return
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

        if _stop_if_canceled(dependencies, job_id, job_root, audio_path):
            return
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
        metadata: dict = {}
        if job.get("job_type", "transcription") == "diarization":
            if not text.strip():
                raise empty_transcript()
            alignment = dependencies.alignment
            diarizer = dependencies.diarization
            if alignment is None or diarizer is None:
                raise RuntimeError("Diarization adapters are unavailable")
            dependencies.jobs.update(job_id, progress=35, current_stage="aligning")
            try:
                alignment_result = alignment.align(
                    audio_path, text=text, segments=segments, language=job.get("language"),
                )
            except AlignmentUnavailable as error:
                raise alignment_failed(str(error)) from error
            if isinstance(alignment_result, list):
                alignment_result = AlignmentResult(
                    words=alignment_result,
                    strategy="whisper_word_timestamps",
                    language=job.get("language"),
                )
            if not alignment_result.words:
                raise alignment_failed("No word timestamps were produced")
            dependencies.jobs.update(job_id, progress=55, current_stage="diarizing")
            turns = diarizer.diarize(
                audio_path,
                min_speakers=job.get("min_speakers"),
                max_speakers=job.get("max_speakers"),
            )
            if not turns:
                raise no_speakers_detected()
            dependencies.jobs.update(job_id, progress=75, current_stage="attributing_speakers")
            attribution = attribute_words(alignment_result.words, turns)
            dependencies.jobs.update(job_id, progress=85, current_stage="segmenting_for_display")
            segments = display_segments(
                attribution.words,
                max_chars_per_line=job.get("max_chars_per_line", 20),
                proportional_timing=not alignment_result.display_word_timestamps_available,
            )
            speakers = sorted({turn["speaker"] for turn in turns})
            metadata.update({
                "alignment_strategy": alignment_result.strategy,
                "alignment_language": alignment_result.language,
                "fallback_used": alignment_result.fallback_used,
                "fallback_reason": alignment_result.fallback_reason,
                "diarization_model": job.get("diarization_model"),
                "diarization_model_revision": job.get("diarization_model_revision"),
                "speaker_count": len(speakers),
                "speakers": speakers,
                "attribution_statistics": attribution.statistics,
                "display_timing_strategy": (
                    "proportional_estimate"
                    if not alignment_result.display_word_timestamps_available
                    else "word_timestamps"
                ),
            })
        dependencies.jobs.update(job_id, progress=90, processed_seconds=duration)

        if _stop_if_canceled(dependencies, job_id, job_root, audio_path):
            return
        dependencies.jobs.update(
            job_id,
            status="processing",
            progress=95,
            current_stage="exporting",
        )
        public_segments = [
            {key: value for key, value in segment.items() if key != "words"}
            for segment in segments
        ]
        artifacts = dependencies.artifacts.write(
            job_id, output_dir=job_root / "result", text=text, language=job["language"],
            duration=duration, model=job["model"], output_script=output_script,
            segments=public_segments, formats=tuple(job.get("output_formats", ("json", "txt", "srt"))),
            job_type=job.get("job_type", "transcription"),
            metadata=metadata,
        )

        if _stop_if_canceled(dependencies, job_id, job_root, audio_path):
            return
        dependencies.jobs.complete(
            job_id,
            text=text,
            artifacts={format: str(path) for format, path in artifacts.items()},
        )
        audio_path.unlink(missing_ok=True)
    except Exception as error:
        failure = classify_failure(error)
        logger.exception("transcription job %s failed with %s", job_id, failure.code)
        discard = getattr(dependencies.artifacts, "discard", None)
        if discard is not None:
            try:
                discard(job_root / "result")
            except Exception:
                logger.exception("failed to discard artifacts for job %s", job_id)
        dependencies.jobs.fail(
            job_id,
            failure.code,
            failure.message,
            retryable=failure.retryable,
        )
    finally:
        stop_heartbeat.set()
        if heartbeat_method is not None:
            heartbeat_thread.join(timeout=settings.heartbeat_interval_seconds)
