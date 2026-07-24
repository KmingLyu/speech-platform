import shutil
from pathlib import Path

from fastapi import UploadFile

from .ports import JobStorage, StoredUpload, UploadTooLarge


class LocalJobStorage(JobStorage):
    def __init__(self, data_root: Path):
        self.jobs_root = data_root / "jobs"

    async def store_upload(
        self,
        job_id: str,
        upload: UploadFile,
        max_size_bytes: int,
    ) -> StoredUpload:
        filename = Path(upload.filename or "upload.bin").name
        source_dir = self.jobs_root / job_id / "source"
        source_dir.mkdir(parents=True, exist_ok=False)
        destination = source_dir / filename
        written = 0
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > max_size_bytes:
                    destination.unlink(missing_ok=True)
                    raise UploadTooLarge
                output.write(chunk)
        return StoredUpload(filename=filename, path=destination)

    def remove_job(self, job_id: str) -> None:
        job_root = self.jobs_root / job_id
        if job_root.exists():
            shutil.rmtree(job_root)

    def artifact_path(self, job: dict, format: str) -> Path | None:
        column = {
            "json": "result_json_path",
            "txt": "result_txt_path",
            "srt": "result_srt_path",
        }[format]
        return Path(job[column]) if job[column] else None
