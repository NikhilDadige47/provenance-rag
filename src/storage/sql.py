"""SQL connection helper: local SQLite file or free Turso Cloud (libSQL).

Set TURSO_DATABASE_URL + TURSO_AUTH_TOKEN to persist sessions and IP quota
on Render Free (no disk). Local dev keeps using a file.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from typing import Any

from dotenv import load_dotenv


def turso_configured() -> bool:
    load_dotenv()
    return bool(os.environ.get("TURSO_DATABASE_URL", "").strip())


class SqlRow(Mapping[str, Any]):
    """Row that supports both sqlite3.Row-style names and integer indexes.

    libsql fetchone() returns a tuple. dict(tuple) then fails with
    'dictionary update sequence element #0 has length N; 2 is required'.
    """

    def __init__(self, values: tuple[Any, ...], columns: list[str]) -> None:
        self._values = values
        self._columns = columns
        self._map = {
            columns[i]: values[i] for i in range(min(len(columns), len(values)))
        }

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._map[key]

    def __iter__(self):
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self):
        return self._columns


class _MappingCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def _wrap(self, row: Any) -> Any:
        if row is None or isinstance(row, (dict, sqlite3.Row, SqlRow)):
            return row
        description = getattr(self._cursor, "description", None)
        if not description:
            return row
        columns = [col[0] for col in description]
        try:
            values = tuple(row)
        except TypeError:
            return row
        return SqlRow(values, columns)

    def execute(self, *args: Any, **kwargs: Any) -> _MappingCursor:
        self._cursor.execute(*args, **kwargs)
        return self

    def fetchone(self) -> Any:
        return self._wrap(self._cursor.fetchone())

    def fetchall(self) -> list[Any]:
        return [self._wrap(row) for row in self._cursor.fetchall()]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _MappingConnection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def cursor(self) -> _MappingCursor:
        return _MappingCursor(self._conn.cursor())

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        result = self._conn.execute(*args, **kwargs)
        if hasattr(result, "fetchone"):
            return _MappingCursor(result)
        return result

    def __enter__(self) -> _MappingConnection:
        if hasattr(self._conn, "__enter__"):
            self._conn.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        if hasattr(self._conn, "__exit__"):
            return self._conn.__exit__(*exc)
        closer = getattr(self._conn, "close", None)
        if closer:
            closer()
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def open_sql_connection(db_path: str, *, timeout: float = 30.0, wal: bool = True) -> Any:
    """Return a sqlite3-compatible connection.

    Turso is used when TURSO_DATABASE_URL is set, ignoring db_path. That is
    how Render Free keeps quota without a persistent disk.
    """
    load_dotenv()
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if url:
        try:
            import libsql
        except ImportError as exc:
            raise RuntimeError(
                "TURSO_DATABASE_URL is set but the libsql package is missing. "
                "Install it with: pip install libsql"
            ) from exc
        conn = libsql.connect(database=url, auth_token=token or None)
        return _MappingConnection(conn)

    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    return conn
