import os
import sys
from pathlib import Path

import httpx

from harness import WORKER_ROOT, run_fake_worker


API_URL = os.environ["API_URL"]


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
    assert payload["source"]["type"] == "upload"


def test_worker_reports_coarse_processing_status_and_pipeline_stage(tmp_path: Path) -> None:
    sys.path.insert(0, str(WORKER_ROOT))
    for module_name in list(sys.modules):
        if module_name == "src" or module_name.startswith("src."):
            del sys.modules[module_name]
    from src.config import Settings
    from src.processor import WorkerDependencies, process_job

    updates: list[dict] = []

    class Jobs:
        def update(self, job_id: str, **changes) -> None:
            updates.append({"job_id": job_id, **changes})

        def complete(self, job_id: str, **_changes) -> None:
            updates.append({"job_id": job_id, "status": "completed"})

        def fail(self, job_id: str, code: str, message: str, *, retryable: bool) -> None:
            raise AssertionError((job_id, code, message, retryable))

    class Sources:
        def acquire(self, _job: dict, _job_root: Path) -> Path:
            source = tmp_path / "source.media"
            source.write_bytes(b"source")
            return source

    class Media:
        def probe_duration(self, _source_path: Path) -> float:
            return 1.0

        def normalize_audio(self, _source_path: Path, output_path: Path) -> Path:
            output_path.parent.mkdir(parents=True)
            output_path.write_bytes(b"audio")
            return output_path

    class Transcription:
        def transcribe(self, _audio_path: Path, *, model_name: str, language: str | None):
            assert model_name == "large-v3-turbo"
            assert language is None
            return "text", [{"start": 0.0, "end": 1.0, "text": "text"}]

    class Converter:
        def convert(self, text: str, segments: list[dict], output_script: str):
            assert output_script == "original"
            return text, segments

    class Artifacts:
        def write(self, _job_id: str, **_kwargs):
            return {
                "json": tmp_path / "result.json",
                "txt": tmp_path / "result.txt",
                "srt": tmp_path / "result.srt",
            }

    process_job(
        Settings(
            database_url="postgresql://unused",
            data_root=tmp_path,
            model_root=tmp_path,
            whisper_model="unused",
            worker_id="fake-worker",
            poll_interval_seconds=0,
            max_attempts=3,
        ),
        WorkerDependencies(
            jobs=Jobs(),
            sources=Sources(),
            media=Media(),
            transcription=Transcription(),
            converter=Converter(),
            artifacts=Artifacts(),
        ),
        {
            "id": "tr_worker",
            "model": "large-v3-turbo",
            "language": None,
            "output_script": "original",
            "output_formats": ("json", "txt", "srt"),
        },
    )

    status_updates = [update for update in updates if "status" in update]
    assert [update["status"] for update in status_updates] == [
        "processing",
        "processing",
        "processing",
        "processing",
        "processing",
        "completed",
    ]
    assert [update["current_stage"] for update in status_updates[:5]] == [
        "acquiring_source",
        "probing",
        "transcoding",
        "transcribing",
        "exporting",
    ]


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
        assert payload["source"]["type"] == "youtube"
        assert payload["artifacts"] == {"json": True, "txt": True, "srt": True}
        assert payload["links"]["artifacts"] == {
            "json": f"{location}?format=json",
            "srt": f"{location}?format=srt",
            "txt": f"{location}?format=txt",
        }
        assert "A deterministic transcript." not in completed.text

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


def test_worker_only_publishes_requested_artifacts() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/transcriptions",
            files=[
                ("youtube_url", (None, "https://www.youtube.com/watch?v=only-json")),
                ("formats", (None, "json")),
            ],
        )
        assert created.status_code == 202
        location = created.headers["Location"]

        run_fake_worker()

        detail = client.get(location)
        json_result = client.get(f"{location}?format=json")
        txt_result = client.get(f"{location}?format=txt")

    assert detail.json()["artifacts"] == {"json": True, "txt": False, "srt": False}
    assert detail.json()["links"]["artifacts"] == {"json": f"{location}?format=json"}
    assert json_result.status_code == 200
    assert txt_result.status_code == 404


def test_job_history_cursor_is_stable_when_new_jobs_are_created() -> None:
    with httpx.Client(base_url=API_URL) as client:
        locations = [
            client.post(
                "/v1/transcriptions",
                data={"youtube_url": f"https://youtu.be/history-{index}"},
            ).headers["Location"]
            for index in range(4)
        ]
        first = client.get("/v1/transcriptions?limit=2")
        newer = client.post(
            "/v1/transcriptions",
            data={"youtube_url": "https://youtu.be/history-newer"},
        )
        second = client.get(
            f"/v1/transcriptions?limit=2&cursor={first.json()['next_cursor']}"
        )
        filtered = client.get("/v1/transcriptions?status=queued&limit=10")

    assert first.status_code == 200
    assert newer.status_code == 202
    assert second.status_code == 200
    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert len(first_ids) == 2
    assert len(second_ids) == 2
    assert first_ids.isdisjoint(second_ids)
    assert newer.json()["id"] not in second_ids
    assert {item["status"] for item in filtered.json()["items"]} == {"queued"}
