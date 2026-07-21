from contextlib import contextmanager

import psycopg

from .config import Settings


@contextmanager
def connection(settings: Settings):
    with psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row) as conn:
        yield conn


def ensure_schema(settings: Settings) -> None:
    """Apply small, backward-compatible schema changes for existing Docker volumes."""
    with connection(settings) as conn:
        conn.execute(
            """
            ALTER TABLE transcription_jobs
            ADD COLUMN IF NOT EXISTS output_script VARCHAR(16) NOT NULL DEFAULT 'original'
            """
        )
        conn.execute(
            """
            ALTER TABLE transcription_jobs
            DROP CONSTRAINT IF EXISTS transcription_jobs_output_script_check
            """
        )
        conn.execute(
            """
            ALTER TABLE transcription_jobs
            ADD CONSTRAINT transcription_jobs_output_script_check
            CHECK (output_script IN ('original', 'traditional', 'simplified'))
            """
        )
        conn.commit()
