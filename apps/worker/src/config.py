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


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        data_root=Path(os.getenv("DATA_ROOT", "/data")),
        model_root=Path(os.getenv("MODEL_ROOT", "/models")),
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
        worker_id=os.getenv("WORKER_ID", "gpu-worker-01"),
        poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "2")),
        max_attempts=int(os.getenv("MAX_ATTEMPTS", "3")),
    )
