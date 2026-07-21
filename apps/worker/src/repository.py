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
                WHERE status = 'queued' AND attempt_count < %s
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
                SET status = 'acquiring_source', current_stage = 'acquiring_source',
                    worker_id = %s, attempt_count = attempt_count + 1,
                    started_at = COALESCE(started_at, NOW()), heartbeat_at = NOW()
                WHERE id = %s
                """,
                (settings.worker_id, job["id"]),
            )
            job["attempt_count"] += 1
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


def complete_job(settings: Settings, job_id: str, *, text: str, json_path: str,
                 txt_path: str, srt_path: str) -> None:
    with db(settings) as conn:
        conn.execute(
            """
            UPDATE transcription_jobs
            SET status = 'completed', progress = 100, current_stage = 'completed',
                result_text = %s, result_json_path = %s, result_txt_path = %s,
                result_srt_path = %s, completed_at = NOW(), heartbeat_at = NOW()
            WHERE id = %s
            """,
            (text, json_path, txt_path, srt_path, job_id),
        )
        conn.commit()


def fail_job(settings: Settings, job_id: str, code: str, message: str) -> None:
    with db(settings) as conn:
        conn.execute(
            """
            UPDATE transcription_jobs
            SET status = 'failed', current_stage = 'failed', error_code = %s,
                error_message = %s, completed_at = NOW(), heartbeat_at = NOW()
            WHERE id = %s
            """,
            (code, message[:2000], job_id),
        )
        conn.commit()
