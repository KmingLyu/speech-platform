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
        assert detail["configuration"]["max_chars_per_line"] == 20
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
        assert [segment["speaker"] for segment in payload["segments"]] == ["SPEAKER_00"] * 3
        assert "".join(segment["text"] for segment in payload["segments"]) == "A deterministic transcript."
        assert all(segment["end"] - segment["start"] <= 5.0 for segment in payload["segments"])
        assert client.get(f"{location}?format=txt").text.count("[SPEAKER_00]") == 3
        assert client.get(f"{location}?format=srt").text.count("[SPEAKER_00]") == 3

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


def test_diarization_accepts_and_preserves_positive_display_line_capacity() -> None:
    with httpx.Client(base_url=API_URL) as client:
        invalid = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/invalid-capacity", "max_chars_per_line": "0"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "invalid_max_chars_per_line"

        created = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/custom-capacity", "max_chars_per_line": "18"},
        )
        assert created.status_code == 202
        location = created.headers["Location"]
        job_id = created.json()["id"]

        detail = client.get(location).json()
        assert detail["configuration"]["max_chars_per_line"] == 18

        run_fake_worker(env={"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "1"})
        assert client.get(location).json()["status"] == "failed"
        retry = client.post(f"/v1/diarizations/{job_id}/retry")
        assert retry.status_code == 202
        assert retry.json()["configuration"]["max_chars_per_line"] == 18

        assert client.get(location).json()["configuration"]["max_chars_per_line"] == 18

        transcription = client.post(
            "/v1/transcriptions",
            data={"youtube_url": "https://youtu.be/transcription-capacity", "max_chars_per_line": "18"},
        )
        assert transcription.status_code == 202
        assert "max_chars_per_line" not in client.get(transcription.headers["Location"]).json()["configuration"]


def test_diarization_prefers_semantic_boundaries_and_preserves_overlong_terms() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={
                "youtube_url": "https://youtu.be/semantic-display",
                "max_chars_per_line": "12",
            },
        )
        assert created.status_code == 202
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SCENARIO": "semantic-display"})
        payload = client.get(f"{location}?format=json").json()

    assert [segment["text"] for segment in payload["segments"]] == ["甲乙。", "丙丁戊己", "PV-1 王小明"]
    assert "".join(segment["text"] for segment in payload["segments"]) == "甲乙。丙丁戊己PV-1 王小明"
    assert payload["segments"][2]["text"] == "PV-1 王小明"

    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/protected-overlong", "max_chars_per_line": "8"},
        )
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SCENARIO": "protected-overlong"})
        protected_payload = client.get(f"{location}?format=json").json()

    assert [segment["text"] for segment in protected_payload["segments"]] == ["PV-1"]


def test_diarization_uses_proportional_display_timing_only_after_attribution() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/display-timing-fallback", "max_chars_per_line": "8"},
        )
        assert created.status_code == 202
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SCENARIO": "display-timing-fallback"})
        payload = client.get(f"{location}?format=json").json()

    assert payload["metadata"]["display_timing_strategy"] == "proportional_estimate"
    assert [segment["text"] for segment in payload["segments"]] == ["abc", "def", "ghi", "jkl"]
    assert [segment["start"] for segment in payload["segments"]] == [0.0, 3.125, 6.25, 9.375]
    assert [segment["end"] for segment in payload["segments"]] == [3.125, 6.25, 9.375, 12.5]
