import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient


API_SERVER_ROOT = Path("/workspace/apps/api-server")


def test_api_persistence_and_storage_can_be_replaced(tmp_path: Path) -> None:
    sys.path.insert(0, str(API_SERVER_ROOT))
    from src.config import Settings
    from src.main import create_app
    from src.ports import NewTranscriptionJob, StoredUpload

    class InMemoryJobs:
        def __init__(self) -> None:
            self.jobs: dict[str, dict] = {}

        def create(self, job: NewTranscriptionJob) -> None:
            self.jobs[job.id] = {
                **job.as_record(),
                "progress": 0,
                "current_stage": None,
                "duration": None,
                "processed_seconds": None,
                "result_text": None,
                "result_json_path": None,
                "result_txt_path": None,
                "result_srt_path": None,
                "error_code": None,
                "error_message": None,
                "created_at": datetime.now(UTC),
                "started_at": None,
                "completed_at": None,
            }

        def get(self, job_id: str) -> dict | None:
            return self.jobs.get(job_id)

    class TemporaryStorage:
        async def store_upload(
            self,
            job_id: str,
            upload,
            max_size_bytes: int,
        ) -> StoredUpload:
            filename = Path(upload.filename or "upload.bin").name
            destination = tmp_path / job_id / filename
            destination.parent.mkdir(parents=True)
            destination.write_bytes(await upload.read())
            return StoredUpload(filename=filename, path=destination)

        def remove_job(self, job_id: str) -> None:
            return None

        def artifact_path(self, job: dict, format: str) -> Path | None:
            return None

    app = create_app(
        settings=Settings(
            database_url="postgresql://unused",
            data_root=tmp_path,
            max_upload_size_bytes=1024,
        ),
        jobs=InMemoryJobs(),
        storage=TemporaryStorage(),
        migrate=lambda: None,
    )

    with TestClient(app) as client:
        created = client.post(
            "/v1/transcriptions",
            files={"file": ("replaceable.wav", b"fixture", "audio/wav")},
        )
        detail = client.get(created.headers["Location"])

    assert created.status_code == 202
    assert detail.status_code == 200
    assert detail.json()["source_type"] == "upload"
    assert detail.json()["status"] == "queued"
