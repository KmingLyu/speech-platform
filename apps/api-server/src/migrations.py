import argparse
import os
from pathlib import Path

import psycopg


DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def migration_files(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[Path]:
    return sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))


def run_migrations(
    database_url: str,
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            migrations = migration_files(migrations_dir)
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext('speech-platform-schema-migrations'))"
            )
            existing_schema_row = conn.execute(
                "SELECT to_regclass('public.transcription_jobs') IS NOT NULL"
            ).fetchone()
            existing_schema = bool(
                existing_schema_row and existing_schema_row[0]
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            applied = {
                row[0]
                for row in conn.execute("SELECT name FROM schema_migrations").fetchall()
            }
            if existing_schema and not applied and migrations:
                baseline = migrations[0].name
                conn.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s)",
                    (baseline,),
                )
                applied.add(baseline)

            for path in migrations:
                if path.name in applied:
                    continue
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s)",
                    (path.name,),
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Speech Platform schema migrations")
    parser.add_argument(
        "database_url",
        nargs="?",
        default=os.environ.get("DATABASE_URL"),
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("database_url or DATABASE_URL is required")
    run_migrations(args.database_url)


if __name__ == "__main__":
    main()
