import os

import httpx

from harness import run_fake_worker


API_URL = os.environ["API_URL"]


def test_diarization_fake_pipeline_exposes_isolated_speaker_artifacts() -> None:
    with httpx.Client(base_url=API_URL) as client:
        invalid = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/fake-diarization", "min_speakers": "3", "max_speakers": "2"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "invalid_speaker_bounds"

        created = client.post(
            "/v1/diarizations",
            data={
                "youtube_url": "https://youtu.be/fake-diarization",
                "language": "en",
                "formats": ["json", "txt", "srt"],
                "min_speakers": "1",
                "max_speakers": "2",
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        location = created.headers["Location"]
        assert job_id.startswith("di_")
        assert client.get(f"/v1/transcriptions/{job_id}").status_code == 404
        detail = client.get(location).json()
        assert detail["job_type"] == "diarization"
        assert detail["configuration"]["min_speakers"] == 1
        assert detail["configuration"]["max_speakers"] == 2
        assert job_id in {item["id"] for item in client.get("/v1/diarizations").json()["items"]}
        assert job_id not in {item["id"] for item in client.get("/v1/transcriptions").json()["items"]}

        run_fake_worker()

        completed = client.get(location).json()
        assert completed["status"] == "completed"
        assert completed["artifacts"] == {"json": True, "txt": True, "srt": True}

        artifact = client.get(f"{location}?format=json")
        payload = artifact.json()
        assert payload["artifact_type"] == "diarized_transcript"
        assert payload["schema_version"] == "1.0"
        assert payload["text"] == "A deterministic transcript."
        assert payload["metadata"]["diarization_model_revision"] == "integration-test-revision"
        assert payload["metadata"]["speaker_count"] == 1
        assert payload["metadata"]["speakers"] == ["SPEAKER_00"]
        assert [segment["speaker"] for segment in payload["segments"]] == ["SPEAKER_00"]
        assert "[SPEAKER_00] A deterministic transcript." in client.get(f"{location}?format=txt").text
        assert "[SPEAKER_00] A deterministic transcript." in client.get(f"{location}?format=srt").text

        assert client.delete(location).status_code == 204
        assert client.get(location).json()["error"]["code"] == "job_not_found"


def test_alignment_falls_back_to_whisper_timestamps_and_records_reason() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/fallback-fixture"},
        )
        assert created.status_code == 202
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SCENARIO": "forced-alignment-fallback"})
        payload = client.get(f"{location}?format=json").json()

    assert payload["metadata"]["alignment_strategy"] == "whisper_word_timestamps"
    assert payload["metadata"]["fallback_used"] is True
    assert payload["metadata"]["fallback_reason"] == "fake forced alignment model unavailable"
