from contextlib import contextmanager
from datetime import datetime

import psycopg

from .config import Settings
from .ports import JobRepository, NewTranscriptionJob


@contextmanager
def connection(settings: Settings):
    with psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row) as conn:
        yield conn


class PostgresJobRepository(JobRepository):
    def __init__(self, settings: Settings):
        self.settings = settings

    def create(self, job: NewTranscriptionJob) -> None:
        with connection(self.settings) as conn:
            conn.execute(
                """
                INSERT INTO transcription_jobs
                    (id, status, source_type, source_url, original_filename,
                     source_path, model, language, output_script, output_formats,
                     job_type, min_speakers, max_speakers)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job.id,
                    job.status,
                    job.source_type,
                    job.source_url,
                    job.original_filename,
                    job.source_path,
                    job.model,
                    job.language,
                    job.output_script,
                    list(job.output_formats),
                    job.job_type,
                    job.min_speakers,
                    job.max_speakers,
                ),
            )
            conn.commit()

    def get(self, job_id: str) -> dict | None:
        with connection(self.settings) as conn:
            return conn.execute(
                "SELECT * FROM transcription_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()

    def retry(self, job_id: str) -> dict | None:
        """Requeue a retryable failed job under the same identity and configuration.

        The automatic-attempt budget is reset so the requeued job can be claimed,
        while the lifetime attempt count keeps the job's execution history.
        """
        with connection(self.settings) as conn:
            job = conn.execute(
                """
                UPDATE transcription_jobs
                SET status = 'queued', current_stage = NULL, progress = 0,
                    automatic_attempt_count = 0, worker_id = NULL,
                    heartbeat_at = NULL, completed_at = NULL
                WHERE id = %s AND status = 'failed' AND error_retryable
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
            return job

    def cancel(self, job_id: str) -> dict | None:
        """Stop an unfinished job: queued jobs cancel immediately, active jobs request it.

        Repeating the request while `cancel_requested` is a no-op that returns the
        current state. Terminal jobs (`completed`, `failed`, `canceled`) match no row,
        so the caller can reject with `job_not_cancelable`.
        """
        with connection(self.settings) as conn:
            job = conn.execute(
                """
                UPDATE transcription_jobs
                SET status = CASE status
                        WHEN 'queued' THEN 'canceled'
                        WHEN 'processing' THEN 'cancel_requested'
                        ELSE status
                    END,
                    current_stage = CASE WHEN status = 'queued' THEN NULL ELSE current_stage END,
                    completed_at = CASE WHEN status = 'queued' THEN NOW() ELSE completed_at END
                WHERE id = %s AND status IN ('queued', 'processing', 'cancel_requested')
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
            return job

    def delete(self, job_id: str) -> dict | None:
        """Remove a terminal job and return its metadata for storage cleanup.

        The status predicate prevents deleting a job while a Worker may still be
        using its source or result files.
        """
        with connection(self.settings) as conn:
            job = conn.execute(
                """
                DELETE FROM transcription_jobs
                WHERE id = %s AND status IN ('completed', 'failed', 'canceled')
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
            return job

    def list(
        self,
        *,
        job_type: str = "transcription",
        status: str | None,
        before: tuple[datetime, str] | None,
        limit: int,
    ) -> list[dict]:
        conditions: list[str] = []
        values: list[object] = []
        conditions.append("job_type = %s")
        values.append(job_type)
        if status is not None:
            conditions.append("status = %s")
            values.append(status)
        if before is not None:
            conditions.append(
                "(created_at < %s OR (created_at = %s AND id < %s))"
            )
            values.extend([before[0], before[0], before[1]])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with connection(self.settings) as conn:
            return conn.execute(
                f"""
                SELECT * FROM transcription_jobs
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                [*values, limit + 1],
            ).fetchall()
