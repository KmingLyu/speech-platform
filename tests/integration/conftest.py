import os
import shutil
from pathlib import Path

import psycopg
import pytest


DATABASE_URL = os.environ["DATABASE_URL"]
DATA_ROOT = Path(os.environ["DATA_ROOT"])


@pytest.fixture(autouse=True)
def isolate_transcription_jobs():
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("TRUNCATE TABLE transcription_jobs")
        conn.commit()
    shutil.rmtree(DATA_ROOT / "jobs", ignore_errors=True)
    yield
