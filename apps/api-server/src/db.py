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
                     source_path, model, language, output_script, output_formats)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                ),
            )
            conn.commit()

    def get(self, job_id: str) -> dict | None:
        with connection(self.settings) as conn:
            return conn.execute(
                "SELECT * FROM transcription_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()

    def list(
        self,
        *,
        status: str | None,
        before: tuple[datetime, str] | None,
        limit: int,
    ) -> list[dict]:
        conditions: list[str] = []
        values: list[object] = []
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
