from contextlib import contextmanager

import psycopg

from .config import Settings


@contextmanager
def connection(settings: Settings):
    with psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row) as conn:
        yield conn
