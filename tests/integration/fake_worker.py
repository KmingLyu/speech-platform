import os
import sys
from pathlib import Path

import psycopg

WORKER_ROOT = Path(__file__).resolve().parents[2] / "apps" / "worker"
sys.path.insert(0, str(WORKER_ROOT))

from src.adapters import FilesystemArtifactWriter, PostgresJobLifecycle
from src.config import Settings
from src.failures import source_download_failed, source_unavailable
from src.processor import (
    ArtifactWriter,
    MediaProcessor,
    SourceAcquirer,
    TranscriptConverter,
    TranscriptionEngine,
    WorkerDependencies,
    process_job,
)
from src.repository import claim_next_job
from src.alignment import ForcedAlignmentWithWhisperFallback, WhisperWordAlignment
from src.diarizer import DiarizationEngine


def _trigger_cancellation(settings: Settings, job_id: str, stage: str, cancel_at: str | None) -> None:
    """Simulate an owner cancel request arriving mid-stage, for checkpoint tests."""
    if cancel_at != stage:
        return
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "UPDATE transcription_jobs SET status = 'cancel_requested' WHERE id = %s",
            (job_id,),
        )
        conn.commit()


class FakeSourceAcquirer(SourceAcquirer):
    """Acquires a deterministic source, or fails the way FAKE_SOURCE_FAILURE asks."""

    def __init__(
        self, failure: str, *, settings: Settings, job_id: str, cancel_at: str | None,
    ) -> None:
        self.failure = failure
        self.settings = settings
        self.job_id = job_id
        self.cancel_at = cancel_at

    def acquire(self, job: dict, job_root: Path) -> Path:
        if self.failure == "retryable":
            raise source_download_failed("fake transient download failure")
        if self.failure == "permanent":
            raise source_unavailable("fake unavailable source")
        if job["source_type"] == "upload":
            source_path = Path(job["source_path"])
        else:
            source_path = job_root / "source" / "fake-youtube.media"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"deterministic fake YouTube source")
        _trigger_cancellation(self.settings, self.job_id, "source", self.cancel_at)
        return source_path


class FakeMediaProcessor(MediaProcessor):
    def __init__(self, *, settings: Settings, job_id: str, cancel_at: str | None) -> None:
        self.settings = settings
        self.job_id = job_id
        self.cancel_at = cancel_at

    def probe_duration(self, source_path: Path) -> float:
        return 12.5

    def normalize_audio(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(source_path.read_bytes())
        _trigger_cancellation(self.settings, self.job_id, "media", self.cancel_at)
        return output_path


class FakeTranscriptionEngine(TranscriptionEngine):
    def __init__(self, *, settings: Settings, job_id: str, cancel_at: str | None) -> None:
        self.settings = settings
        self.job_id = job_id
        self.cancel_at = cancel_at

    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        language: str | None,
    ) -> tuple[str, list[dict]]:
        _trigger_cancellation(self.settings, self.job_id, "transcription", self.cancel_at)
        scenario = os.getenv("FAKE_SCENARIO", "default")
        if scenario == "empty-transcript":
            return "", []
        if scenario == "alternating":
            return "Hello world again", [{
                "id": 0, "start": 0.0, "end": 3.0, "text": "Hello world again",
                "words": [
                    {"start": 0.0, "end": 1.0, "text": "Hello"},
                    {"start": 1.0, "end": 2.0, "text": " world"},
                    {"start": 2.0, "end": 3.0, "text": " again"},
                ],
            }]
        if scenario == "partial-attribution":
            return "Hello mystery goodbye", [{
                "id": 0, "start": 0.0, "end": 3.0, "text": "Hello mystery goodbye",
                "words": [
                    {"start": 0.0, "end": 1.0, "text": "Hello"},
                    {"start": 1.5, "end": 2.0, "text": " mystery"},
                    {"start": 2.0, "end": 3.0, "text": " goodbye"},
                ],
            }]
        return (
            "A deterministic transcript.",
            [{
                "id": 0, "start": 0.0, "end": 12.5,
                "text": "A deterministic transcript.",
                "words": [{"start": 0.0, "end": 12.5, "text": "A deterministic transcript."}],
            }],
        )


class ControlledDiarizationEngine(DiarizationEngine):
    def diarize(self, audio_path: Path, *, min_speakers: int | None, max_speakers: int | None) -> list[dict]:
        del audio_path, min_speakers, max_speakers
        scenario = os.getenv("FAKE_SCENARIO", "default")
        if scenario == "no-speakers":
            return []
        if scenario == "alternating":
            return [
                {"start": 0.0, "end": 1.2, "speaker": "SPEAKER_00"},
                {"start": 1.2, "end": 3.0, "speaker": "SPEAKER_01"},
            ]
        if scenario == "partial-attribution":
            return [
                {"start": 0.0, "end": 1.1, "speaker": "SPEAKER_00"},
                {"start": 2.2, "end": 3.0, "speaker": "SPEAKER_01"},
            ]
        return [{"start": 0.0, "end": 12.5, "speaker": "SPEAKER_00"}]


class IdentityTranscriptConverter(TranscriptConverter):
    def convert(
        self,
        text: str,
        segments: list[dict],
        output_script: str,
    ) -> tuple[str, list[dict]]:
        return text, segments


class FailingForcedAlignment:
    def align(self, audio_path: Path, *, text: str, segments: list[dict], language: str | None):
        del audio_path, text, segments, language
        raise RuntimeError("fake forced alignment model unavailable")


class CancelSimulatingArtifactWriter(ArtifactWriter):
    """Wraps the real writer so 'export' cancellation can be simulated mid-stage."""

    def __init__(
        self, inner: ArtifactWriter, *, settings: Settings, job_id: str, cancel_at: str | None,
    ) -> None:
        self.inner = inner
        self.settings = settings
        self.job_id = job_id
        self.cancel_at = cancel_at

    def write(self, job_id: str, **kwargs) -> dict[str, Path]:
        artifacts = self.inner.write(job_id, **kwargs)
        _trigger_cancellation(self.settings, self.job_id, "export", self.cancel_at)
        return artifacts

    def discard(self, output_dir: Path) -> None:
        self.inner.discard(output_dir)


def main() -> None:
    settings = Settings(
        database_url=os.environ["DATABASE_URL"],
        data_root=Path(os.environ["DATA_ROOT"]),
        model_root=Path(os.environ["MODEL_ROOT"]),
        whisper_model="unused",
        worker_id=os.environ["WORKER_ID"],
        poll_interval_seconds=0,
        max_attempts=int(os.environ["MAX_ATTEMPTS"]),
        heartbeat_interval_seconds=float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5")),
        stale_timeout_seconds=float(os.getenv("STALE_TIMEOUT_SECONDS", "30")),
    )
    job = claim_next_job(settings)
    if job is None:
        raise RuntimeError("No queued Transcription job is available")
    cancel_at = os.getenv("FAKE_CANCEL_AT")
    job_id = job["id"]
    dependencies = WorkerDependencies(
        jobs=PostgresJobLifecycle(settings),
        sources=FakeSourceAcquirer(
            os.getenv("FAKE_SOURCE_FAILURE", ""), settings=settings, job_id=job_id, cancel_at=cancel_at,
        ),
        media=FakeMediaProcessor(settings=settings, job_id=job_id, cancel_at=cancel_at),
        transcription=FakeTranscriptionEngine(settings=settings, job_id=job_id, cancel_at=cancel_at),
        converter=IdentityTranscriptConverter(),
        artifacts=CancelSimulatingArtifactWriter(
            FilesystemArtifactWriter(), settings=settings, job_id=job_id, cancel_at=cancel_at,
        ),
        alignment=(
            ForcedAlignmentWithWhisperFallback(FailingForcedAlignment(), WhisperWordAlignment())
            if os.getenv("FAKE_SCENARIO") == "forced-alignment-fallback"
            else WhisperWordAlignment()
        ),
        diarization=ControlledDiarizationEngine(),
    )
    process_job(settings, dependencies, job)


if __name__ == "__main__":
    main()
