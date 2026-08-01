import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_root: Path
    model_root: Path
    whisper_model: str
    worker_id: str
    poll_interval_seconds: float
    max_attempts: int
    heartbeat_interval_seconds: float = 5
    stale_timeout_seconds: float = 30
    diarization_model: str = "pyannote/speaker-diarization-community-1"
    diarization_model_revision: str | None = None
    inference_device: str = "auto"


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        data_root=Path(os.getenv("DATA_ROOT", "/data")),
        model_root=Path(os.getenv("MODEL_ROOT", "/models")),
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
        worker_id=os.getenv("WORKER_ID", "gpu-worker-01"),
        poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "2")),
        max_attempts=int(os.getenv("MAX_ATTEMPTS", "3")),
        heartbeat_interval_seconds=float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5")),
        stale_timeout_seconds=float(os.getenv("STALE_TIMEOUT_SECONDS", "30")),
        diarization_model=os.getenv(
            "DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1"
        ),
        diarization_model_revision=os.getenv("DIARIZATION_MODEL_REVISION"),
        inference_device=os.getenv("INFERENCE_DEVICE", "auto"),
    )
