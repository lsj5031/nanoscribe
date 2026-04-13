"""System API endpoints – health, capabilities."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["system"])

DATA_DIR = Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))


def _check_db() -> str:
    """Check if the SQLite database is accessible and has a valid schema."""
    db_path = DATA_DIR / "nanoscribe.db"
    try:
        conn = sqlite3.connect(str(db_path))
        # integrity_check verifies the database file is valid
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            return "ok"
        return "error"
    except Exception:
        return "error"


def _check_storage() -> str:
    """Check if the data directory is writable."""
    try:
        test_file = DATA_DIR / ".healthcheck_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return "ok"
    except Exception:
        return "error"


@router.get("/health")
async def health_check() -> dict:
    """Return component-level health status.

    Always returns HTTP 200 — health checks are informational, not errors.
    Individual components report their own status.
    """
    return {
        "status": "ok",
        "backend": "ok",
        "db": _check_db(),
        "storage": _check_storage(),
        "model_ready": False,  # Will be updated when ASR model loading is implemented
    }
