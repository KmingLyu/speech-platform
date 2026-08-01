import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "large-v3-turbo"
SUPPORTED_OUTPUT_FORMATS = frozenset({"json", "txt", "srt"})


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_root: Path
    max_upload_size_bytes: int
    supported_models: frozenset[str] = frozenset({DEFAULT_MODEL})
    diarization_model: str = "pyannote/speaker-diarization-community-1"
    diarization_model_revision: str | None = None


def load_settings() -> Settings:
    max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "2048"))
    configured_models = os.getenv("SUPPORTED_MODELS", DEFAULT_MODEL)
    supported_models = frozenset(
        {DEFAULT_MODEL}
        | {model.strip() for model in configured_models.split(",") if model.strip()}
    )
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        data_root=Path(os.getenv("DATA_ROOT", "/data")),
        max_upload_size_bytes=max_upload_size_mb * 1024 * 1024,
        supported_models=supported_models,
        diarization_model=os.getenv(
            "DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1"
        ),
        diarization_model_revision=os.getenv("DIARIZATION_MODEL_REVISION"),
    )
