import os

import httpx

from harness import run_fake_worker


API_URL = os.environ["API_URL"]


def _create_diarization(client: httpx.Client) -> str:
    response = client.post(
        "/v1/diarizations",
        data={"youtube_url": "https://youtu.be/controlled-alignment-fixture"},
    )
    assert response.status_code == 202
    return response.headers["Location"]


def test_word_attribution_regroups_crossing_asr_segment_sequentially() -> None:
    with httpx.Client(base_url=API_URL) as client:
        location = _create_diarization(client)
        run_fake_worker(env={"FAKE_SCENARIO": "alternating"})

        payload = client.get(f"{location}?format=json").json()

    assert payload["segments"] == [
        {"id": 0, "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Hello"},
        {"id": 1, "start": 1.0, "end": 3.0, "speaker": "SPEAKER_01", "text": "world again"},
    ]
    assert all("words" not in segment for segment in payload["segments"])
    assert "diarization_turns" not in payload


def test_partial_word_attribution_is_publicly_unknown_and_records_statistics() -> None:
    with httpx.Client(base_url=API_URL) as client:
        location = _create_diarization(client)
        run_fake_worker(env={"FAKE_SCENARIO": "partial-attribution"})

        payload = client.get(f"{location}?format=json").json()
        txt = client.get(f"{location}?format=txt").text
        srt = client.get(f"{location}?format=srt").text

    assert [segment["speaker"] for segment in payload["segments"]] == [
        "SPEAKER_00", None, "SPEAKER_01"
    ]
    assert payload["metadata"]["attribution_statistics"] == {
        "word_count": 3,
        "attributed_word_count": 2,
        "unattributed_word_count": 1,
    }
    assert "[UNKNOWN] mystery" in txt
    assert "[UNKNOWN] mystery" in srt


def test_display_artifacts_split_at_capacity_and_reliable_speaker_changes() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={
                "youtube_url": "https://youtu.be/display-segments",
                "max_chars_per_line": "10",
            },
        )
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SCENARIO": "display-segments"})

        segments = client.get(f"{location}?format=json").json()["segments"]
        txt = client.get(f"{location}?format=txt").text
        srt = client.get(f"{location}?format=srt").text

    assert segments == [
        {"id": 0, "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Hello"},
        {"id": 1, "start": 1.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "there"},
        {"id": 2, "start": 2.0, "end": 3.0, "speaker": "SPEAKER_01", "text": "again"},
        {"id": 3, "start": 3.0, "end": 4.0, "speaker": "SPEAKER_01", "text": "world"},
    ]
    assert all("\n" not in segment["text"] for segment in segments)
    assert all(segment["end"] - segment["start"] >= 1.0 for segment in segments)
    assert txt.splitlines() == [
        "[SPEAKER_00] Hello",
        "[SPEAKER_00] there",
        "[SPEAKER_01] again",
        "[SPEAKER_01] world",
    ]
    assert srt.count("[SPEAKER_00]") == 2
    assert srt.count("[SPEAKER_01]") == 2


def test_display_cues_extend_short_timing_to_a_readable_duration() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/display-timing"},
        )
        location = created.headers["Location"]
        run_fake_worker(env={"FAKE_SCENARIO": "display-timing"})
        segments = client.get(f"{location}?format=json").json()["segments"]

    assert segments == [{
        "id": 0,
        "start": 0.0,
        "end": 1.0,
        "speaker": "SPEAKER_00",
        "text": "abcdefghijkl",
    }]
    assert all(1.0 <= segment["end"] - segment["start"] <= 5.0 for segment in segments)
    assert all(len(segment["text"]) * 0.5 / (segment["end"] - segment["start"]) <= 6.0 for segment in segments)


def test_empty_transcription_is_a_permanent_failure() -> None:
    with httpx.Client(base_url=API_URL) as client:
        location = _create_diarization(client)
        run_fake_worker(env={"FAKE_SCENARIO": "empty-transcript"})
        payload = client.get(location).json()

    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "empty_transcript",
        "message": "The transcription produced no text.",
        "retryable": False,
    }


def test_no_detected_speakers_is_a_permanent_failure() -> None:
    with httpx.Client(base_url=API_URL) as client:
        location = _create_diarization(client)
        run_fake_worker(env={"FAKE_SCENARIO": "no-speakers"})
        payload = client.get(location).json()

    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "no_speakers_detected",
        "message": "No speakers were detected in the audio.",
        "retryable": False,
    }
