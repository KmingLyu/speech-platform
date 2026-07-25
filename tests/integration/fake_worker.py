import os
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[2] / "apps" / "worker"
sys.path.insert(0, str(WORKER_ROOT))

from src.adapters import FilesystemArtifactWriter, PostgresJobLifecycle
from src.config import Settings
from src.processor import (
    MediaProcessor,
    SourceAcquirer,
    TranscriptConverter,
    TranscriptionEngine,
    WorkerDependencies,
    process_job,
)
from src.repository import claim_next_job


class FakeSourceAcquirer(SourceAcquirer):
    def acquire(self, job: dict, job_root: Path) -> Path:
        if job["source_type"] == "upload":
            return Path(job["source_path"])
        source_path = job_root / "source" / "fake-youtube.media"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"deterministic fake YouTube source")
        return source_path


class FakeMediaProcessor(MediaProcessor):
    def probe_duration(self, source_path: Path) -> float:
        return 12.5

    def normalize_audio(self, source_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(source_path.read_bytes())
        return output_path


class FakeTranscriptionEngine(TranscriptionEngine):
    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        language: str | None,
    ) -> tuple[str, list[dict]]:
        return (
            "A deterministic transcript.",
            [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 12.5,
                    "text": "A deterministic transcript.",
                }
            ],
        )


class IdentityTranscriptConverter(TranscriptConverter):
    def convert(
        self,
        text: str,
        segments: list[dict],
        output_script: str,
    ) -> tuple[str, list[dict]]:
        return text, segments


def main() -> None:
    settings = Settings(
        database_url=os.environ["DATABASE_URL"],
        data_root=Path(os.environ["DATA_ROOT"]),
        model_root=Path(os.environ["MODEL_ROOT"]),
        whisper_model="unused",
        worker_id=os.environ["WORKER_ID"],
        poll_interval_seconds=0,
        max_attempts=int(os.environ["MAX_ATTEMPTS"]),
    )
    job = claim_next_job(settings)
    if job is None:
        raise RuntimeError("No queued Transcription job is available")
    dependencies = WorkerDependencies(
        jobs=PostgresJobLifecycle(settings),
        sources=FakeSourceAcquirer(),
        media=FakeMediaProcessor(),
        transcription=FakeTranscriptionEngine(),
        converter=IdentityTranscriptConverter(),
        artifacts=FilesystemArtifactWriter(),
    )
    process_job(settings, dependencies, job)


if __name__ == "__main__":
    main()
