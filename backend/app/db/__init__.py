"""Database connection management and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path


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
    """
    try:
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            return "ok"
        return "error"
    except Exception:
        return "error"
