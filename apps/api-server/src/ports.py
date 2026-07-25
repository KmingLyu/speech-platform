from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile


@dataclass(frozen=True)
class NewTranscriptionJob:
    id: str
    source_type: str
    source_url: str | None
    original_filename: str | None
    source_path: str | None
    model: str
    language: str | None
    output_script: str
    output_formats: tuple[str, ...] = ("json", "txt", "srt")
    status: str = "queued"

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StoredUpload:
    filename: str
    path: Path


class UploadTooLarge(RuntimeError):
    pass


class JobRepository(Protocol):
    def create(self, job: NewTranscriptionJob) -> None: ...

    def get(self, job_id: str) -> dict | None: ...

    def list(
        self,
        *,
        status: str | None,
        before: tuple[datetime, str] | None,
        limit: int,
    ) -> list[dict]: ...

    def retry(self, job_id: str) -> dict | None: ...


class JobStorage(Protocol):
    async def store_upload(
        self,
        job_id: str,
        upload: UploadFile,
        max_size_bytes: int,
    ) -> StoredUpload: ...

    def remove_job(self, job_id: str) -> None: ...

    def artifact_path(self, job: dict, format: str) -> Path | None: ...
