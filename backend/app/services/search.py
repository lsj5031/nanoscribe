"""Search service – FTS5 full-text search across memo titles and segment text."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

MAX_RESULTS = 50
SEGMENT_PREVIEW_LENGTH = 200


def search(
    db_path: str | Path,
    query: str,
) -> dict[str, Any]:
    """Search memos by title and segment text using FTS5.

    Returns {"results": [...], "total": N}.
    """
    q = query.strip()
    if not q:
        return {"results": [], "total": 0}

    safe_q = _escape_fts_query(q)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        results: list[dict[str, Any]] = []

        # Use FTS5 to find candidate memo IDs (handles fuzzy/tokenized matching)
        matching_memo_ids = _find_matching_memo_ids(conn, safe_q)

        if not matching_memo_ids:
            return {"results": [], "total": 0}

        placeholders = ",".join("?" for _ in matching_memo_ids)

        # Title matches: check which matching memos have the query in their title
        title_rows = conn.execute(
            f"SELECT m.id AS memo_id, m.title AS memo_title "
            f"FROM memos m "
            f"WHERE m.id IN ({placeholders}) AND m.title LIKE ?",
            [*matching_memo_ids, f"%{q}%"],
        ).fetchall()

        for row in title_rows:
            results.append(
                {
                    "memo_id": row["memo_id"],
                    "memo_title": row["memo_title"],
                    "match_type": "title",
                    "segment_id": None,
                    "segment_text": None,
                    "start_ms": None,
                    "end_ms": None,
                }
            )

        # Segment matches: find segments of matching memos that contain the query
        seg_rows = conn.execute(
            f"SELECT s.id AS segment_id, s.memo_id AS memo_id, "
            f"s.text AS segment_text, s.start_ms, s.end_ms, "
            f"m.title AS memo_title "
            f"FROM segments s "
            f"JOIN memos m ON m.id = s.memo_id "
            f"WHERE s.memo_id IN ({placeholders}) AND s.text LIKE ?",
            [*matching_memo_ids, f"%{q}%"],
        ).fetchall()

        for row in seg_rows:
            text = row["segment_text"] or ""
            preview = text[:SEGMENT_PREVIEW_LENGTH] if len(text) > SEGMENT_PREVIEW_LENGTH else text
            results.append(
                {
                    "memo_id": row["memo_id"],
                    "memo_title": row["memo_title"],
                    "match_type": "segment",
                    "segment_id": row["segment_id"],
                    "segment_text": preview,
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                }
            )

        # Enforce limit
        total = len(results)
        results = results[:MAX_RESULTS]

        return {"results": results, "total": total}
    finally:
        conn.close()


def _escape_fts_query(q: str) -> str:
    """Escape FTS5 special characters in a search query."""
    escaped = q.replace('"', '""')
    return f'"{escaped}"'


def _find_matching_memo_ids(conn: sqlite3.Connection, safe_q: str) -> list[str]:
    """Find memo IDs that match the FTS5 query in title or segment text."""
    try:
        title_matches = conn.execute(
            "SELECT m.id FROM memos m WHERE m.rowid IN (SELECT rowid FROM memos_fts WHERE memos_fts MATCH ?)",
            (safe_q,),
        ).fetchall()
    except sqlite3.OperationalError:
        title_matches = []

    try:
        seg_matches = conn.execute(
            "SELECT DISTINCT s.memo_id FROM segments s WHERE s.rowid IN "
            "(SELECT rowid FROM memos_fts WHERE memos_fts MATCH ?)",
            (safe_q,),
        ).fetchall()
    except sqlite3.OperationalError:
        seg_matches = []

    ids: set[str] = set()
    for (memo_id,) in title_matches:
        ids.add(memo_id)
    for (memo_id,) in seg_matches:
        ids.add(memo_id)

    return list(ids)
