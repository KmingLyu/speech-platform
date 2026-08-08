import os

import httpx
import pytest

from harness import run_fake_worker


API_URL = os.environ["API_URL"]

RESOURCES = ["transcriptions", "diarizations"]


def create_job(
    client: httpx.Client, resource: str, hotwords: list[str], **fields: str
) -> httpx.Response:
    return client.post(
        f"/v1/{resource}",
        files=[
            ("youtube_url", (None, f"https://youtu.be/hotwords-{resource}")),
            *((key, (None, value)) for key, value in fields.items()),
            *(("hotwords", (None, hotword)) for hotword in hotwords),
        ],
    )


@pytest.mark.parametrize("resource", RESOURCES)
def test_accepted_hotwords_are_echoed_in_the_job_configuration(resource: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, ["PV-1", "Meta-Energy"])
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.status_code == 200
    assert detail.json()["configuration"]["hotwords"] == ["PV-1", "Meta-Energy"]


@pytest.mark.parametrize("resource", RESOURCES)
def test_omitting_hotwords_leaves_the_job_configuration_empty(resource: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, [])
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.json()["configuration"]["hotwords"] == []


def test_diarization_exposes_hotwords_alongside_its_own_configuration() -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(
            client, "diarizations", ["PV-1"], min_speakers="1", max_speakers="2",
            max_chars_per_line="18",
        )
        assert created.status_code == 202
        configuration = client.get(created.headers["Location"]).json()["configuration"]

    assert configuration["hotwords"] == ["PV-1"]
    assert configuration["min_speakers"] == 1
    assert configuration["max_speakers"] == 2
    assert configuration["max_chars_per_line"] == 18


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize(
    ("language", "hotword", "expected"),
    [
        ("zh-tw", "软件", "軟體"),
        ("zh-cn", "軟體", "软件"),
        ("en", "软件", "软件"),
    ],
)
def test_hotwords_are_converted_to_the_jobs_output_script(
    resource: str, language: str, hotword: str, expected: str,
) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, [hotword], language=language)
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.json()["configuration"]["hotwords"] == [expected]


@pytest.mark.parametrize("resource", RESOURCES)
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
    resource: str, hotwords: list[str], message: str,
) -> None:
    with httpx.Client(base_url=API_URL) as client:
        rejected = create_job(client, resource, hotwords)
        history = client.get(f"/v1/{resource}")

    assert rejected.status_code == 422
    assert rejected.json() == {"error": {"code": "invalid_hotwords", "message": message}}
    assert history.json()["items"] == []


@pytest.mark.parametrize("resource", RESOURCES)
@pytest.mark.parametrize("hotword", ["x" * 50, " PV-1 "])
def test_hotwords_at_the_edge_of_the_limits_are_accepted(resource: str, hotword: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, [hotword])
        assert created.status_code == 202
        detail = client.get(created.headers["Location"])

    assert detail.json()["configuration"]["hotwords"] == [hotword.strip()]


@pytest.mark.parametrize("resource", RESOURCES)
def test_the_recognizer_receives_the_joined_converted_hotwords(resource: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, ["软件", "PV-1"], language="zh-tw")
        location = created.headers["Location"]

        run_fake_worker(env={"FAKE_SCENARIO": "echo-hotwords"})

        artifact = client.get(f"{location}?format=json")

    assert artifact.status_code == 200
    assert artifact.json()["text"] == "hotword hint: '軟體 PV-1'"


@pytest.mark.parametrize("resource", RESOURCES)
def test_a_job_without_hotwords_sends_no_hint_to_the_recognizer(resource: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, [])
        location = created.headers["Location"]

        run_fake_worker(env={"FAKE_SCENARIO": "echo-hotwords"})

        artifact = client.get(f"{location}?format=json")

    assert artifact.json()["text"] == "hotword hint: None"


@pytest.mark.parametrize("resource", RESOURCES)
def test_retry_reuses_the_original_hotwords(resource: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        created = create_job(client, resource, ["软件", "PV-1"], language="zh-tw")
        location = created.headers["Location"]
        job_id = created.json()["id"]

        run_fake_worker(env={"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "1"})
        failed = client.get(location).json()

        retried = client.post(f"/v1/{resource}/{job_id}/retry")
        run_fake_worker(env={"FAKE_SCENARIO": "echo-hotwords"})

        completed = client.get(location).json()
        artifact = client.get(f"{location}?format=json")

    assert failed["status"] == "failed"
    assert retried.status_code == 202
    assert retried.json()["configuration"]["hotwords"] == ["軟體", "PV-1"]
    assert completed["status"] == "completed"
    assert completed["configuration"]["hotwords"] == ["軟體", "PV-1"]
    assert artifact.json()["text"] == "hotword hint: '軟體 PV-1'"
