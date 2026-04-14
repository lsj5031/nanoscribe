"""Segments service – fetch ordered transcript segments for a memo."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _row_to_segment(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a segments row to a dict."""
    return {
        "id": row["id"],
        "ordinal": row["ordinal"],
        "start_ms": row["start_ms"],
        "end_ms": row["end_ms"],
        "text": row["text"],
        "speaker_key": row["speaker_key"],
        "confidence": row["confidence"],
        "edited": bool(row["edited"]),
    }


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

        segments = [_row_to_segment(row) for row in rows]

        return {
            "memo_id": memo["id"],
            "revision": memo["transcript_revision"],
            "segments": segments,
        }
    finally:
        conn.close()


class ConflictError(Exception):
    """Raised when base_revision does not match current transcript_revision."""

    def __init__(self, current_revision: int, current_segments: list[dict[str, Any]]) -> None:
        self.current_revision = current_revision
        self.current_segments = current_segments
        super().__init__("Conflict: transcript has been modified")


def patch_segments(
    db_path: str | Path,
    memo_id: str,
    base_revision: int,
    updates: list[dict[str, str]],
) -> dict[str, Any]:
    """Update segment texts with optimistic concurrency.

    Args:
        db_path: Path to the SQLite database.
        memo_id: The memo ID.
        base_revision: The revision the client based its edits on.
        updates: List of {"segment_id": ..., "text": ...} dicts.

    Returns:
        {"memo_id": ..., "revision": N, "updated_segments": [...]}

    Raises:
        FileNotFoundError: If the memo does not exist.
        ConflictError: If base_revision doesn't match current revision.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        memo = conn.execute(
            "SELECT id, transcript_revision FROM memos WHERE id = ?",
            (memo_id,),
        ).fetchone()
        if memo is None:
            raise FileNotFoundError("Memo not found")

        current_revision = memo["transcript_revision"]

        if not updates:
            return {
                "memo_id": memo_id,
                "revision": current_revision,
                "updated_segments": [],
            }

        if base_revision != current_revision:
            rows = conn.execute(
                "SELECT id, ordinal, start_ms, end_ms, text, speaker_key, confidence, edited "
                "FROM segments WHERE memo_id = ? ORDER BY ordinal",
                (memo_id,),
            ).fetchall()
            raise ConflictError(
                current_revision=current_revision,
                current_segments=[_row_to_segment(r) for r in rows],
            )

        new_revision = current_revision + 1
        updated_segments: list[dict[str, Any]] = []

        for upd in updates:
            seg_id = upd["segment_id"]
            new_text = upd["text"]
            conn.execute(
                "UPDATE segments SET text = ?, edited = 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
                "WHERE id = ? AND memo_id = ?",
                (new_text, seg_id, memo_id),
            )

        conn.execute(
            "UPDATE memos SET transcript_revision = ?, "
            "last_edited_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ?",
            (new_revision, memo_id),
        )
        conn.commit()

        # Fetch updated segments
        seg_ids = [upd["segment_id"] for upd in updates]
        placeholders = ",".join("?" for _ in seg_ids)
        rows = conn.execute(
            "SELECT id, ordinal, start_ms, end_ms, text, speaker_key, confidence, edited "
            f"FROM segments WHERE id IN ({placeholders}) ORDER BY ordinal",
            seg_ids,
        ).fetchall()
        updated_segments = [_row_to_segment(r) for r in rows]

        return {
            "memo_id": memo_id,
            "revision": new_revision,
            "updated_segments": updated_segments,
        }
    finally:
        conn.close()
