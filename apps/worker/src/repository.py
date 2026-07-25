from contextlib import contextmanager
from typing import Any

import psycopg

from .config import Settings


@contextmanager
def db(settings: Settings):
    with psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row) as conn:
        yield conn


def claim_next_job(settings: Settings) -> dict[str, Any] | None:
    with db(settings) as conn:
        with conn.transaction():
            job = conn.execute(
                """
                SELECT * FROM transcription_jobs
                WHERE status = 'queued' AND automatic_attempt_count < %s
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (settings.max_attempts,),
            ).fetchone()
            if job is None:
                return None
            conn.execute(
                """
                UPDATE transcription_jobs
                SET status = 'processing', current_stage = 'acquiring_source',
                    worker_id = %s, attempt_count = attempt_count + 1,
                    automatic_attempt_count = automatic_attempt_count + 1,
                    started_at = COALESCE(started_at, NOW()), heartbeat_at = NOW()
                WHERE id = %s
                """,
                (settings.worker_id, job["id"]),
            )
            job["attempt_count"] += 1
            job["automatic_attempt_count"] += 1
            return job


def update_job(settings: Settings, job_id: str, *, status: str | None = None,
               progress: int | None = None, current_stage: str | None = None,
               duration: float | None = None, processed_seconds: float | None = None,
               **extra: Any) -> None:
    fields: dict[str, Any] = {"heartbeat_at": "NOW()"}
    if status is not None:
        fields["status"] = status
    if progress is not None:
        fields["progress"] = progress
    if current_stage is not None:
        fields["current_stage"] = current_stage
    if duration is not None:
        fields["duration"] = duration
    if processed_seconds is not None:
        fields["processed_seconds"] = processed_seconds
    fields.update(extra)

    assignments: list[str] = []
    values: list[Any] = []
    for column, value in fields.items():
        if value == "NOW()":
            assignments.append(f"{column} = NOW()")
        else:
            assignments.append(f"{column} = %s")
            values.append(value)
    values.append(job_id)
    with db(settings) as conn:
        conn.execute(f"UPDATE transcription_jobs SET {', '.join(assignments)} WHERE id = %s", values)
        conn.commit()


def complete_job(settings: Settings, job_id: str, *, text: str,
                 artifacts: dict[str, str]) -> None:
    with db(settings) as conn:
        conn.execute(
            """
            UPDATE transcription_jobs
            SET status = 'completed', progress = 100, current_stage = NULL,
                result_text = %s, result_json_path = %s, result_txt_path = %s,
                result_srt_path = %s, completed_at = NOW(), heartbeat_at = NOW(),
                error_code = NULL, error_message = NULL, error_retryable = NULL
            WHERE id = %s
            """,
            (text, artifacts.get("json"), artifacts.get("txt"), artifacts.get("srt"), job_id),
        )
        conn.commit()


def cancel_if_requested(settings: Settings, job_id: str) -> bool:
    """Confirm cancellation at a safe checkpoint between processing stages.

    Only a job still marked `cancel_requested` is stopped here; anything else
    (including a job that was never asked to cancel) is left untouched.
    """
    with db(settings) as conn:
        with conn.transaction():
            job = conn.execute(
                "SELECT status FROM transcription_jobs WHERE id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if job is None or job["status"] != "cancel_requested":
                return False
            conn.execute(
                """
                UPDATE transcription_jobs
                SET status = 'canceled', current_stage = NULL, progress = 0,
                    result_text = NULL, result_json_path = NULL,
                    result_txt_path = NULL, result_srt_path = NULL,
                    worker_id = NULL, heartbeat_at = NULL, completed_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            return True


def fail_job(
    settings: Settings,
    job_id: str,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> None:
    """Record a failed Attempt, requeueing only while the automatic budget remains."""
    with db(settings) as conn:
        with conn.transaction():
            job = conn.execute(
                """
                SELECT status, automatic_attempt_count FROM transcription_jobs
                WHERE id = %s
                FOR UPDATE
                """,
                (job_id,),
            ).fetchone()
            if job is None or job["status"] != "processing":
                return
            failure = (code, message[:2000], retryable, job_id)
            if retryable and job["automatic_attempt_count"] < settings.max_attempts:
                conn.execute(
                    """
                    UPDATE transcription_jobs
                    SET status = 'queued', current_stage = NULL, progress = 0,
                        error_code = %s, error_message = %s, error_retryable = %s,
                        result_text = NULL, result_json_path = NULL,
                        result_txt_path = NULL, result_srt_path = NULL,
                        worker_id = NULL, heartbeat_at = NULL, completed_at = NULL
                    WHERE id = %s
                    """,
                    failure,
                )
                return
            conn.execute(
                """
                UPDATE transcription_jobs
                SET status = 'failed', current_stage = NULL,
                    error_code = %s, error_message = %s, error_retryable = %s,
                    result_text = NULL, result_json_path = NULL,
                    result_txt_path = NULL, result_srt_path = NULL,
                    completed_at = NOW(), heartbeat_at = NOW()
                WHERE id = %s
                """,
                failure,
            )
