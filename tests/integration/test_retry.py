import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
import pytest

from harness import run_fake_worker


API_URL = os.environ["API_URL"]
DATABASE_URL = os.environ["DATABASE_URL"]
STALE_HEARTBEAT = datetime.now(UTC) - timedelta(hours=1)


def create_queued_job(client: httpx.Client, **fields: str) -> str:
    response = client.post(
        "/v1/transcriptions",
        data={"youtube_url": "https://youtu.be/retry-fixture", **fields},
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


def test_retry_rejects_an_unknown_job() -> None:
    with httpx.Client(base_url=API_URL) as client:
        response = client.post("/v1/transcriptions/tr_missing/retry")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "job_not_found", "message": "Transcription job not found"}
    }


@pytest.mark.parametrize(
    ("status", "error_retryable"),
    [
        ("queued", None),
        ("processing", None),
        ("cancel_requested", None),
        ("canceled", None),
        ("completed", None),
        ("failed", False),
        ("failed", None),
    ],
)
def test_retry_is_rejected_unless_the_job_failed_retryably(
    status: str, error_retryable: bool | None,
) -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(job_id, status=status, error_retryable=error_retryable)

        response = client.post(f"/v1/transcriptions/{job_id}/retry")
        detail = client.get(f"/v1/transcriptions/{job_id}")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "job_not_retryable",
            "message": "Transcription job cannot be retried",
        }
    }
    assert detail.json()["status"] == status


def test_retryable_failures_requeue_only_while_the_automatic_budget_remains() -> None:
    bounded_retryable = {"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "2"}
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)

        run_fake_worker(env=bounded_retryable)
        requeued = client.get(f"/v1/transcriptions/{job_id}").json()

        run_fake_worker(env=bounded_retryable)
        exhausted = client.get(f"/v1/transcriptions/{job_id}").json()

        run_fake_worker(env=bounded_retryable, check=False)
        beyond_budget = client.get(f"/v1/transcriptions/{job_id}").json()

    assert requeued["status"] == "queued"
    assert requeued["attempts"] == {"count": 1, "automatic_count": 1}
    assert requeued["error"] == {
        "code": "source_download_failed",
        "message": "The source could not be downloaded.",
        "retryable": True,
    }
    assert requeued["current_stage"] is None
    assert exhausted["status"] == "failed"
    assert exhausted["attempts"] == {"count": 2, "automatic_count": 2}
    assert exhausted["error"]["retryable"] is True
    assert beyond_budget == exhausted


def test_permanent_failures_are_terminal_and_reject_manual_retry() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)

        run_fake_worker(env={"FAKE_SOURCE_FAILURE": "permanent"})
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

        retried = client.post(f"/v1/transcriptions/{job_id}/retry")
        run_fake_worker(check=False)
        beyond_failure = client.get(f"/v1/transcriptions/{job_id}").json()

    assert detail["status"] == "failed"
    assert detail["error"] == {
        "code": "source_unavailable",
        "message": "The requested source is unavailable.",
        "retryable": False,
    }
    assert detail["attempts"] == {"count": 1, "automatic_count": 1}
    assert detail["artifacts"] == {"json": False, "txt": False, "srt": False}
    assert retried.status_code == 409
    assert retried.json()["error"]["code"] == "job_not_retryable"
    assert beyond_failure == detail


def test_manual_retry_preserves_job_identity_and_configuration() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client, language="zh-tw", formats="srt")
        force_columns(
            job_id,
            status="failed",
            error_code="source_download_failed",
            error_message="The source could not be downloaded.",
            error_retryable=True,
            attempt_count=3,
            automatic_attempt_count=3,
            progress=40,
        )
        failed = client.get(f"/v1/transcriptions/{job_id}").json()

        retried = client.post(f"/v1/transcriptions/{job_id}/retry")

        requeued = client.get(f"/v1/transcriptions/{job_id}").json()

    assert failed["status"] == "failed"
    assert retried.status_code == 202
    payload = retried.json()
    assert payload["id"] == job_id
    assert payload["status"] == "queued"
    assert payload["configuration"] == failed["configuration"]
    assert payload["source"] == failed["source"]
    assert payload["attempts"] == {"count": 3, "automatic_count": 0}
    assert requeued["status"] == "queued"
    assert requeued["configuration"] == {
        "model": "large-v3-turbo",
        "language": "zh-tw",
        "formats": ["srt"],
        "hotwords": [],
    }
    assert requeued["progress"] == 0


def test_a_retried_job_is_processed_again_under_the_same_identity() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        run_fake_worker(env={"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "1"})
        failed = client.get(f"/v1/transcriptions/{job_id}").json()

        retried = client.post(f"/v1/transcriptions/{job_id}/retry")
        run_fake_worker()

        completed = client.get(f"/v1/transcriptions/{job_id}").json()
        history = client.get("/v1/transcriptions").json()

    assert failed["status"] == "failed"
    assert failed["error"] == {
        "code": "source_download_failed",
        "message": "The source could not be downloaded.",
        "retryable": True,
    }
    assert retried.status_code == 202
    assert completed["id"] == job_id
    assert completed["status"] == "completed"
    assert completed["error"] is None
    assert completed["attempts"] == {"count": 2, "automatic_count": 1}
    assert completed["artifacts"] == {"json": True, "txt": True, "srt": True}
    assert [item["id"] for item in history["items"]] == [job_id]


def test_stale_processing_job_is_requeued_as_worker_lost() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(
            job_id,
            status="processing",
            worker_id="dead-worker",
            heartbeat_at=STALE_HEARTBEAT,
            attempt_count=1,
            automatic_attempt_count=1,
        )

        run_fake_worker(env={"STALE_TIMEOUT_SECONDS": "1"})
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

    assert detail["status"] == "completed"
    assert detail["attempts"] == {"count": 2, "automatic_count": 2}


def test_stale_recovery_exhaustion_is_a_stable_worker_lost_failure() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(
            job_id,
            status="processing",
            worker_id="dead-worker",
            heartbeat_at=STALE_HEARTBEAT,
            attempt_count=3,
            automatic_attempt_count=3,
        )

        run_fake_worker(env={"STALE_TIMEOUT_SECONDS": "1"}, check=False)
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

    assert detail["status"] == "failed"
    assert detail["error"] == {
        "code": "worker_lost",
        "message": "The Worker stopped responding.",
        "retryable": True,
    }


def test_stale_recovery_does_not_requeue_cancel_requested_jobs() -> None:
    with httpx.Client(base_url=API_URL) as client:
        job_id = create_queued_job(client)
        force_columns(
            job_id,
            status="cancel_requested",
            worker_id="dead-worker",
            heartbeat_at=STALE_HEARTBEAT,
            attempt_count=1,
            automatic_attempt_count=1,
        )

        run_fake_worker(check=False)
        detail = client.get(f"/v1/transcriptions/{job_id}").json()

    assert detail["status"] == "cancel_requested"
