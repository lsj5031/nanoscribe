"""Database connection management and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.migrate import run_migrations  # noqa: F401


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled.

    Caller is responsible for closing the connection.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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

        conn = sqlite3.connect(str(db_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                return "error"

            # Verify expected schema tables exist
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memos'").fetchall()
            if not tables:
                return "error"
        finally:
            conn.close()

        return "ok"
    except Exception:
        return "error"
