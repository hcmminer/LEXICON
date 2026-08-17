from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from warehouse.config import SQL_DIR, database_url


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        yield conn


def executemany(conn: psycopg.Connection, sql: str, rows) -> None:
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def migrate() -> None:
    schema = (SQL_DIR / "001_schema.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(schema)
        conn.commit()


def execute_sql_file(path: Path, params: dict | None = None) -> None:
    sql = path.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(sql, params or {})
        conn.commit()
