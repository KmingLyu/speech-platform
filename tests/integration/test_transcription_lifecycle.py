import os
import subprocess
import sys
from pathlib import Path

import httpx


API_URL = os.environ["API_URL"]
WORKER_ROOT = Path("/workspace/apps/worker")
FAKE_WORKER = Path("/workspace/tests/integration/fake_worker.py")


def run_fake_worker() -> None:
    subprocess.run(
        [sys.executable, str(FAKE_WORKER)],
        cwd=WORKER_ROOT,
        check=True,
    )


def test_uploaded_source_job_can_be_created_and_polled() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/transcriptions",
            files={"file": ("fixture.wav", b"deterministic audio fixture", "audio/wav")},
        )

        assert created.status_code == 202
        job = created.json()
        assert job["status"] == "queued"
        assert created.headers["Location"] == f"/v1/transcriptions/{job['id']}"

        detail = client.get(created.headers["Location"])

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["id"] == job["id"]
    assert payload["status"] == "queued"
    assert payload["source_type"] == "upload"


def test_fake_youtube_job_completes_and_artifacts_can_be_downloaded() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/transcriptions",
            data={"youtube_url": "https://www.youtube.com/watch?v=fake-fixture"},
        )
        assert created.status_code == 202
        location = created.headers["Location"]
        assert client.get(location).json()["status"] == "queued"

        run_fake_worker()

        completed = client.get(location)
        assert completed.status_code == 200
        payload = completed.json()
        assert payload["status"] == "completed"
        assert payload["source_type"] == "youtube"
        assert payload["result"] == {
            "text": "A deterministic transcript.",
            "available_formats": ["json", "txt", "srt"],
        }

        result_json = client.get(f"{location}?format=json")
        result_txt = client.get(f"{location}?format=txt")
        result_srt = client.get(f"{location}?format=srt")

    assert result_json.status_code == 200
    assert result_json.json()["segments"] == [
        {
            "id": 0,
            "start": 0.0,
            "end": 12.5,
            "text": "A deterministic transcript.",
        }
    ]
    assert result_txt.text == "A deterministic transcript.\n"
    assert "00:00:00,000 --> 00:00:12,500" in result_srt.text
