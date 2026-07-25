import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


DATABASE_URL = os.environ["DATABASE_URL"]
API_SERVER_ROOT = Path("/workspace/apps/api-server")
LEGACY_SCHEMA = Path("/workspace/tests/integration/fixtures/legacy_schema.sql")


@contextmanager
def temporary_database():
    database_name = f"migration_{uuid4().hex}"
    connection_options = conninfo_to_dict(DATABASE_URL)
    admin_database_url = make_conninfo(**{**connection_options, "dbname": "speech_test"})
    test_database_url = make_conninfo(**{**connection_options, "dbname": database_name})

    with psycopg.connect(admin_database_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        yield test_database_url
    finally:
        with psycopg.connect(admin_database_url, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))


def run_migrations(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "src.migrations", database_url],
        cwd=API_SERVER_ROOT,
        check=True,
    )


def test_schema_migrations_are_repeatable_on_clean_database() -> None:
    with temporary_database() as database_url:
        run_migrations(database_url)
        run_migrations(database_url)

        with psycopg.connect(database_url) as conn:
            table_exists = conn.execute(
                "SELECT to_regclass('public.transcription_jobs') IS NOT NULL"
            ).fetchone()[0]
            applied = conn.execute(
                "SELECT name FROM schema_migrations ORDER BY name"
            ).fetchall()

    assert table_exists is True
    assert applied == [
        ("001_create_transcription_jobs.sql",),
        ("002_add_output_script.sql",),
        ("003_add_output_formats.sql",),
        ("004_add_retry_classification.sql",),
    ]


def test_schema_migrations_upgrade_existing_database() -> None:
    with temporary_database() as database_url:
        with psycopg.connect(database_url) as conn:
            conn.execute(LEGACY_SCHEMA.read_text(encoding="utf-8"))
            conn.commit()

        run_migrations(database_url)

        with psycopg.connect(database_url) as conn:
            output_script = conn.execute(
                """
                SELECT column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'transcription_jobs'
                  AND column_name = 'output_script'
                """
            ).fetchone()
            applied = conn.execute(
                "SELECT name FROM schema_migrations ORDER BY name"
            ).fetchall()

    assert output_script == ("'original'::character varying", "NO")
    assert applied == [
        ("001_create_transcription_jobs.sql",),
        ("002_add_output_script.sql",),
        ("003_add_output_formats.sql",),
        ("004_add_retry_classification.sql",),
    ]


def test_schema_migrations_carry_existing_attempts_into_the_automatic_budget() -> None:
    with temporary_database() as database_url:
        with psycopg.connect(database_url) as conn:
            conn.execute(LEGACY_SCHEMA.read_text(encoding="utf-8"))
            conn.execute(
                """
                INSERT INTO transcription_jobs
                    (id, status, source_type, source_url, model, attempt_count,
                     error_code, error_message)
                VALUES ('tr_legacy', 'failed', 'youtube', 'https://youtu.be/legacy',
                        'large-v3-turbo', 2, 'processing_failed', 'Legacy failure')
                """
            )
            conn.commit()

        run_migrations(database_url)

        with psycopg.connect(database_url) as conn:
            legacy = conn.execute(
                """
                SELECT attempt_count, automatic_attempt_count, error_retryable
                FROM transcription_jobs WHERE id = 'tr_legacy'
                """
            ).fetchone()

    assert legacy == (2, 2, None)
