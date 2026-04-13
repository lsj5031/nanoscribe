"""FastAPI dependency injection helpers."""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    return get_settings()


def settings_dep() -> Settings:
    """FastAPI dependency that provides application settings."""
    return _cached_settings()


def get_db_connection(settings: Settings | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled.

    Caller is responsible for closing the connection.
    """
    if settings is None:
        settings = get_settings()
    conn = sqlite3.connect(str(settings.db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
