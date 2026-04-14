"""Speakers service – fetch and update memo-local speakers, create diarization jobs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import db_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_speakers(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Fetch all speakers for a memo from memo_speakers table.

    Returns None if the memo does not exist.
    """
    with db_connection(db_path) as conn:
        memo = conn.execute("SELECT id FROM memos WHERE id = ?", (memo_id,)).fetchone()
        if memo is None:
            return None

        rows = conn.execute(
            "SELECT id, speaker_key, display_name, color FROM memo_speakers WHERE memo_id = ? ORDER BY rowid",
            (memo_id,),
        ).fetchall()

        speakers = [
            {
                "id": row[0],
                "speaker_key": row[1],
                "display_name": row[2],
                "color": row[3],
            }
            for row in rows
        ]

        return {"memo_id": memo_id, "speakers": speakers}


def update_speakers(
    db_path: str | Path,
    memo_id: str,
    updates: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Update display_name and color for speakers.

    Args:
        db_path: Path to the SQLite database.
        memo_id: The memo ID.
        updates: List of {"speaker_key": ..., "display_name": ..., "color": ...} dicts.

    Returns:
        {"memo_id": ..., "speakers": [...]} or None if memo not found.
    """
    with db_connection(db_path) as conn:
        memo = conn.execute("SELECT id FROM memos WHERE id = ?", (memo_id,)).fetchone()
        if memo is None:
            return None

        now = _now_iso()
        for upd in updates:
            conn.execute(
                "UPDATE memo_speakers SET display_name = ?, color = ?, updated_at = ? "
                "WHERE memo_id = ? AND speaker_key = ?",
                (upd["display_name"], upd["color"], now, memo_id, upd["speaker_key"]),
            )
        conn.commit()

        # Return updated speakers
        rows = conn.execute(
            "SELECT id, speaker_key, display_name, color FROM memo_speakers WHERE memo_id = ? ORDER BY rowid",
            (memo_id,),
        ).fetchall()

        speakers = [
            {
                "id": row[0],
                "speaker_key": row[1],
                "display_name": row[2],
                "color": row[3],
            }
            for row in rows
        ]

        return {"memo_id": memo_id, "speakers": speakers}


def create_diarization_job(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Create a diarization-only job for a memo.

    Returns the new job dict, or None if memo not found.
    Raises ValueError if an active job already exists for this memo.
    """
    with db_connection(db_path) as conn:
        memo = conn.execute("SELECT id FROM memos WHERE id = ?", (memo_id,)).fetchone()
        if memo is None:
            return None

        # Check for active jobs
        active_job = conn.execute(
            "SELECT id FROM jobs WHERE memo_id = ? AND status NOT IN (?, ?, ?)",
            (memo_id, "completed", "failed", "cancelled"),
        ).fetchone()
        if active_job is not None:
            raise ValueError("Memo has an active job")

        # Delete existing speakers (they will be recreated by diarization)
        conn.execute("DELETE FROM memo_speakers WHERE memo_id = ?", (memo_id,))

        # Create a diarize job
        job_id = str(uuid.uuid4())
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO jobs
                (id, memo_id, job_type, status, stage, progress,
                 attempt_count, enable_diarization, created_at)
            VALUES (?, ?, 'diarize', 'queued', NULL, 0.0, 1, 1, ?)
            """,
            (job_id, memo_id, now),
        )

        # Update memo status to queued
        conn.execute(
            "UPDATE memos SET status = 'queued', updated_at = ? WHERE id = ?",
            (now, memo_id),
        )
        conn.commit()

        # Fetch and return the job
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        col_names = [desc[0] for desc in conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).description]
        return dict(zip(col_names, row))
