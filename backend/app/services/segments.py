"""Segments service – fetch ordered transcript segments for a memo."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def get_segments(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Return ordered segments and revision for a memo.

    Returns None if the memo does not exist.
    Returns {"memo_id": ..., "revision": N, "segments": [...]} otherwise.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        # Check memo exists and get revision
        memo = conn.execute(
            "SELECT id, transcript_revision FROM memos WHERE id = ?",
            (memo_id,),
        ).fetchone()
        if memo is None:
            return None

        rows = conn.execute(
            "SELECT id, ordinal, start_ms, end_ms, text, speaker_key, confidence, edited "
            "FROM segments WHERE memo_id = ? ORDER BY ordinal",
            (memo_id,),
        ).fetchall()

        segments = []
        for row in rows:
            segments.append(
                {
                    "id": row["id"],
                    "ordinal": row["ordinal"],
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                    "text": row["text"],
                    "speaker_key": row["speaker_key"],
                    "confidence": row["confidence"],
                    "edited": bool(row["edited"]),
                }
            )

        return {
            "memo_id": memo["id"],
            "revision": memo["transcript_revision"],
            "segments": segments,
        }
    finally:
        conn.close()
