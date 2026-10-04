import os

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    share_token TEXT NOT NULL UNIQUE,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True)


def init():
    with connect() as conn:
        conn.execute(SCHEMA)


def ping() -> bool:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False
