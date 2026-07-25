import os
from typing import Any

import httpx
import psycopg
import pytest

from harness import run_fake_worker


API_URL = os.environ["API_URL"]
DATABASE_URL = os.environ["DATABASE_URL"]


def create_queued_job(client: httpx.Client, **fields: str) -> str:
    response = client.post(
        "/v1/transcriptions",
        data={"youtube_url": "https://youtu.be/cancel-fixture", **fields},
    )
    assert response.status_code == 202
    return response.json()["id"]


def force_columns(job_id: str, **columns: Any) -> None:
    """Place a job in a lifecycle state the current API cannot reach on its own."""
    assignments = ", ".join(f"{column} = %s" for column in columns)
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            f"UPDATE transcription_jobs SET {assignments} WHERE id = %s",
            [*columns.values(), job_id],
        )
        conn.commit()


def test_cancel_rejects_an_unknown_job() -> None:
    with httpx.Client(base_url=API_URL) as client:
        response = client.post("/v1/transcriptions/tr_missing/cancel")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "job_not_found", "message": "Transcription job not found"}
    }


def test_canceling_a_queued_job_cancels_immediately_without_a_worker_attempt() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)

        response = client.post(f"/v1/transcriptions/{job_id}/cancel")
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "canceled"
    assert payload["attempts"] == {"count": 0, "automatic_count": 0}
    assert detail["status"] == "canceled"
    assert detail["attempts"] == {"count": 0, "automatic_count": 0}


def test_canceling_a_processing_job_returns_202_and_records_cancel_requested() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(
            job_id,
            status="processing",
            current_stage="transcribing",
            worker_id="fake-worker-01",
            attempt_count=1,
            automatic_attempt_count=1,
        )

        response = client.post(f"/v1/transcriptions/{job_id}/cancel")
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "cancel_requested"
    assert payload["current_stage"] == "transcribing"
    assert detail["status"] == "cancel_requested"
    assert detail["current_stage"] == "transcribing"


def test_repeating_a_cancel_request_while_active_is_idempotent() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(
            job_id,
            status="processing",
            current_stage="transcoding",
            worker_id="fake-worker-01",
        )

        first = client.post(f"/v1/transcriptions/{job_id}/cancel")
        second = client.post(f"/v1/transcriptions/{job_id}/cancel")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()
    assert second.json()["status"] == "cancel_requested"


def test_repeating_a_cancel_request_once_canceled_is_rejected() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)

        first = client.post(f"/v1/transcriptions/{job_id}/cancel")
        second = client.post(f"/v1/transcriptions/{job_id}/cancel")
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

    assert first.status_code == 200
    assert first.json()["status"] == "canceled"
    assert second.status_code == 409
    assert second.json() == {
        "error": {
            "code": "job_not_cancelable",
            "message": "Transcription job cannot be canceled",
        }
    }
    assert detail["status"] == "canceled"


@pytest.mark.parametrize("status", ["completed", "failed", "canceled"])
def test_cancel_is_rejected_once_a_job_reaches_a_terminal_state(status: str) -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(job_id, status=status)

        response = client.post(f"/v1/transcriptions/{job_id}/cancel")
        detail = client.get(f"/v1/transcriptions/{job_id}")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "job_not_cancelable",
            "message": "Transcription job cannot be canceled",
        }
    }
    assert detail.json()["status"] == status


@pytest.mark.parametrize("stage", ["source", "media", "transcription", "export"])
def test_worker_stops_at_the_next_safe_checkpoint_after_cancellation_is_requested(
    stage: str,
) -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)

        run_fake_worker(env={"FAKE_CANCEL_AT": stage})

        detail = client.get(f"/v1/transcriptions/{job_id}").json()
        json_result = client.get(f"/v1/transcriptions/{job_id}?format=json")

    assert detail["status"] == "canceled"
    assert detail["current_stage"] is None
    assert detail["progress"] == 0
    assert detail["artifacts"] == {"json": False, "txt": False, "srt": False}
    assert detail["attempts"] == {"count": 1, "automatic_count": 1}
    assert json_result.status_code == 409
    assert json_result.json()["error"]["code"] == "result_not_ready"
