"""Database connection management and migration runner."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.db.migrate import run_migrations  # noqa: F401


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled.

    Caller is responsible for closing the connection.
    Prefer ``db_connection`` for automatic cleanup via context manager.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_connection(
    db_path: str | Path,
    *,
    row_factory: type | None = None,
) -> Iterator[sqlite3.Connection]:
    """Context manager for SQLite connections with WAL mode and foreign keys.

    Ensures the connection is always closed, even if an exception occurs.

    Usage::

        with db_connection(db_path) as conn:
            conn.execute(...)
            conn.commit()

    Args:
        db_path: Path to the SQLite database file.
        row_factory: Optional row factory (e.g. sqlite3.Row).
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if row_factory is not None:
        conn.row_factory = row_factory
    try:
        yield conn
    finally:
        conn.close()


def in_placeholders(count: int) -> str:
    """Return comma-separated ``?`` placeholders for SQL IN clauses.

    Avoids f-string SQL construction by generating the placeholder string
    from a known count.  Values are always passed as parameters.

    Example::

        ph = in_placeholders(len(statuses))
        conn.execute(f"SELECT * FROM jobs WHERE status IN ({ph})", statuses)
    """
    return ",".join("?" for _ in range(count))


def check_db_health(db_path: str | Path) -> str:
    """Check if the SQLite database is accessible and has a valid schema.

    Returns:
        "ok" if the database is healthy, "error" otherwise.

    VAL-SYS-004: sqlite3.connect() creates a new empty file if the DB doesn't
    exist, so we must explicitly check the file exists AND has the expected
    schema (e.g., 'memos' table) before reporting healthy.
    """
    try:
        path = Path(db_path)
        if not path.exists():
            return "error"

        with db_connection(db_path) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                return "error"

            # Verify expected schema tables exist
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memos'").fetchall()
            if not tables:
                return "error"

        return "ok"
    except Exception:
        return "error"
