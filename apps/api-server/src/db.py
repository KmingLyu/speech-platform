from contextlib import contextmanager

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
                     source_path, model, language, output_script)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                ),
            )
            conn.commit()

    def get(self, job_id: str) -> dict | None:
        with connection(self.settings) as conn:
            return conn.execute(
                "SELECT * FROM transcription_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
