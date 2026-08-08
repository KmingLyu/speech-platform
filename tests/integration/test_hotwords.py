import os

import httpx
import pytest

from harness import run_fake_worker


API_URL = os.environ["API_URL"]


def create_transcription(client: httpx.Client, hotwords: list[str], **fields: str) -> httpx.Response:
    return client.post(
        "/v1/transcriptions",
        files=[
            ("youtube_url", (None, "https://youtu.be/hotwords-fixture")),
            *((key, (None, value)) for key, value in fields.items()),
            *(("hotwords", (None, hotword)) for hotword in hotwords),
        ],
    )


def test_accepted_hotwords_are_echoed_in_the_job_configuration() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, ["PV-1", "Meta-Energy"])
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.status_code == 200
    assert detail.json()["configuration"]["hotwords"] == ["PV-1", "Meta-Energy"]


def test_omitting_hotwords_leaves_the_job_configuration_empty() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, [])
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.json()["configuration"]["hotwords"] == []


def test_diarization_configuration_does_not_advertise_hotwords_yet() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/diarizations",
            data={"youtube_url": "https://youtu.be/hotwords-diarization"},
        )
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert "hotwords" not in detail.json()["configuration"]


@pytest.mark.parametrize(
    ("language", "hotword", "expected"),
    [
        ("zh-tw", "软件", "軟體"),
        ("zh-cn", "軟體", "软件"),
        ("en", "软件", "软件"),
    ],
)
def test_hotwords_are_converted_to_the_jobs_output_script(
    language: str, hotword: str, expected: str,
) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, [hotword], language=language)
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.json()["configuration"]["hotwords"] == [expected]


@pytest.mark.parametrize(
    ("hotwords", "message"),
    [
        ([""], "hotwords must not be empty"),
        (["   "], "hotwords must not be empty"),
        (["PV-1", ""], "hotwords must not be empty"),
        (["x" * 51], "each hotword must be at most 50 characters"),
        ([f"hotword-{index}" for index in range(101)], "hotwords must contain at most 100 entries"),
    ],
)
def test_invalid_hotwords_are_rejected_without_creating_a_job(
    hotwords: list[str], message: str,
) -> None:
    with httpx.Client(base_url=API_URL) as client:
        rejected = create_transcription(client, hotwords)
        history = client.get("/v1/transcriptions")

    assert rejected.status_code == 422
    assert rejected.json() == {"error": {"code": "invalid_hotwords", "message": message}}
    assert history.json()["items"] == []


@pytest.mark.parametrize("hotword", ["x" * 50, " PV-1 "])
def test_hotwords_at_the_edge_of_the_limits_are_accepted(hotword: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, [hotword])
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.json()["configuration"]["hotwords"] == [hotword.strip()]


def test_the_recognizer_receives_the_joined_converted_hotwords() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, ["软件", "PV-1"], language="zh-tw")
        location = created.headers["Location"]

        run_fake_worker(env={"FAKE_SCENARIO": "echo-hotwords"})

        transcript = client.get(f"{location}?format=txt")

    assert transcript.status_code == 200
    assert transcript.text == "hotword hint: '軟體 PV-1'\n"


def test_a_job_without_hotwords_sends_no_hint_to_the_recognizer() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, [])
        location = created.headers["Location"]

        run_fake_worker(env={"FAKE_SCENARIO": "echo-hotwords"})

        transcript = client.get(f"{location}?format=txt")

    assert transcript.text == "hotword hint: None\n"


def test_retry_reuses_the_original_hotwords() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_transcription(client, ["软件", "PV-1"], language="zh-tw")
        location = created.headers["Location"]
        job_id = created.json()["id"]

        run_fake_worker(env={"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "1"})
        failed = client.get(location).json()

        retried = client.post(f"/v1/transcriptions/{job_id}/retry")
        run_fake_worker(env={"FAKE_SCENARIO": "echo-hotwords"})

        completed = client.get(location).json()
        transcript = client.get(f"{location}?format=txt")

    assert failed["status"] == "failed"
    assert retried.status_code == 202
    assert retried.json()["configuration"]["hotwords"] == ["軟體", "PV-1"]
    assert completed["status"] == "completed"
    assert completed["configuration"]["hotwords"] == ["軟體", "PV-1"]
    assert transcript.text == "hotword hint: '軟體 PV-1'\n"
