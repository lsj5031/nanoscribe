"""SQLite migration runner.

Applies numbered SQL migration files from the migrations/ directory.
Tracks applied migrations in a _migrations table for idempotency.
Enables WAL mode and foreign key constraints on each connection.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional, Union

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_DEFAULT_DB_DIR = Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "nanoscribe.db"


def run_migrations(db_path: Optional[Union[str, Path]] = None) -> None:
    """Apply all pending migrations to the database.

    Creates the database file if it doesn't exist. Creates the _migrations
    tracking table. Applies each .sql file in order, recording each in
    _migrations. Safe to call multiple times (idempotent).

    Args:
        db_path: Path to the SQLite database file. Defaults to
                 $NANOSCRIBE_DATA_DIR/nanoscribe.db.
    """
    if db_path is None:
        db_path = _DEFAULT_DB_PATH
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        # Create migration tracking table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                name TEXT PRIMARY KEY NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.commit()

        # Get already-applied migrations
        applied = {row[0] for row in conn.execute("SELECT name FROM _migrations").fetchall()}

        # Find and apply pending migrations in sorted order
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for mf in migration_files:
            name = mf.name
            if name in applied:
                continue

            sql = mf.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
            conn.commit()

    finally:
        conn.close()
