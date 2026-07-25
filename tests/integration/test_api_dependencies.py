import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
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
    assert detail.json()["source"]["type"] == "upload"
    assert detail.json()["status"] == "queued"


def test_job_detail_is_compact_and_exposes_lifecycle_metadata(tmp_path: Path) -> None:
    sys.path.insert(0, str(API_SERVER_ROOT))
    from src.config import Settings
    from src.main import create_app

    job = {
        "id": "tr_processing",
        "status": "processing",
        "progress": 42,
        "current_stage": "transcribing",
        "source_type": "upload",
        "model": "large-v3-turbo",
        "language": "en",
        "output_script": "original",
        "duration": 12.5,
        "processed_seconds": 8.0,
        "created_at": datetime(2026, 7, 25, tzinfo=UTC),
        "started_at": datetime(2026, 7, 25, 0, 0, 1, tzinfo=UTC),
        "completed_at": None,
        "result_text": "must not be exposed in detail",
        "result_json_path": None,
        "result_txt_path": None,
        "result_srt_path": None,
        "error_code": None,
        "error_message": None,
    }

    class Jobs:
        def create(self, _job) -> None:
            raise AssertionError("not used")

        def get(self, job_id: str) -> dict | None:
            return job if job_id == job["id"] else None

    class Storage:
        async def store_upload(self, *_args, **_kwargs):
            raise AssertionError("not used")

        def remove_job(self, _job_id: str) -> None:
            raise AssertionError("not used")

        def artifact_path(self, _job: dict, _format: str) -> Path | None:
            return None

    app = create_app(
        settings=Settings(
            database_url="postgresql://unused",
            data_root=tmp_path,
            max_upload_size_bytes=1024,
        ),
        jobs=Jobs(),
        storage=Storage(),
        migrate=lambda: None,
    )

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/v1/transcriptions/tr_processing")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "id": "tr_processing",
        "status": "processing",
        "current_stage": "transcribing",
        "progress": 42,
        "source": {"type": "upload"},
        "configuration": {
            "model": "large-v3-turbo",
            "language": "en",
            "output_script": "original",
        },
        "timing": {
            "duration": 12.5,
            "processed_seconds": 8.0,
            "created_at": "2026-07-25T00:00:00Z",
            "started_at": "2026-07-25T00:00:01Z",
            "completed_at": None,
        },
        "error": None,
        "artifacts": {"json": False, "txt": False, "srt": False},
    }
    assert "must not be exposed in detail" not in response.text


@pytest.mark.parametrize(
    "status",
    ["queued", "processing", "completed", "failed", "cancel_requested", "canceled"],
)
def test_job_detail_supports_every_public_lifecycle_status(
    tmp_path: Path, status: str,
) -> None:
    sys.path.insert(0, str(API_SERVER_ROOT))
    from src.config import Settings
    from src.main import create_app

    job = {
        "id": "tr_status",
        "status": status,
        "progress": 100 if status == "completed" else 10,
        "current_stage": "transcribing" if status == "processing" else None,
        "source_type": "youtube",
        "model": "large-v3-turbo",
        "language": None,
        "output_script": "original",
        "duration": None,
        "processed_seconds": None,
        "created_at": datetime(2026, 7, 25, tzinfo=UTC),
        "started_at": None,
        "completed_at": None,
        "result_text": "private transcript",
        "result_json_path": "/data/result.json" if status == "completed" else None,
        "result_txt_path": "/data/result.txt" if status == "completed" else None,
        "result_srt_path": "/data/result.srt" if status == "completed" else None,
        "error_code": "processing_failed" if status == "failed" else None,
        "error_message": "Transcription processing failed." if status == "failed" else None,
    }

    class Jobs:
        def create(self, _job) -> None:
            raise AssertionError("not used")

        def get(self, job_id: str) -> dict | None:
            return job if job_id == job["id"] else None

    class Storage:
        async def store_upload(self, *_args, **_kwargs):
            raise AssertionError("not used")

        def remove_job(self, _job_id: str) -> None:
            raise AssertionError("not used")

        def artifact_path(self, _job: dict, _format: str) -> Path | None:
            return None

    app = create_app(
        settings=Settings(
            database_url="postgresql://unused",
            data_root=tmp_path,
            max_upload_size_bytes=1024,
        ),
        jobs=Jobs(),
        storage=Storage(),
        migrate=lambda: None,
    )

    with TestClient(app) as client:
        response = client.get("/v1/transcriptions/tr_status")

    assert response.status_code == 200
    assert response.json()["status"] == status
    assert "private transcript" not in response.text


def test_api_errors_use_a_structured_sanitized_envelope(tmp_path: Path) -> None:
    sys.path.insert(0, str(API_SERVER_ROOT))
    from src.config import Settings
    from src.main import create_app

    class Jobs:
        def create(self, _job) -> None:
            raise AssertionError("not used")

        def get(self, _job_id: str) -> dict | None:
            return None

    class Storage:
        async def store_upload(self, *_args, **_kwargs):
            raise AssertionError("not used")

        def remove_job(self, _job_id: str) -> None:
            raise AssertionError("not used")

        def artifact_path(self, _job: dict, _format: str) -> Path | None:
            return None

    app = create_app(
        settings=Settings(
            database_url="postgresql://unused",
            data_root=tmp_path,
            max_upload_size_bytes=1024,
        ),
        jobs=Jobs(),
        storage=Storage(),
        migrate=lambda: None,
    )

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        missing = client.get("/v1/transcriptions/missing")
        invalid = client.post("/v1/transcriptions")

    assert missing.status_code == 404
    assert missing.json() == {
        "error": {"code": "job_not_found", "message": "Transcription job not found"}
    }
    assert invalid.status_code == 422
    assert invalid.json() == {
        "error": {
            "code": "invalid_source",
            "message": "Provide exactly one of file or youtube_url",
        }
    }
