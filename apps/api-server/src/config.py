import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_root: Path
    max_upload_size_bytes: int


def load_settings() -> Settings:
    max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "2048"))
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        data_root=Path(os.getenv("DATA_ROOT", "/data")),
        max_upload_size_bytes=max_upload_size_mb * 1024 * 1024,
    )
