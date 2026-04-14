"""Search service – FTS5 full-text search across memo titles and segment text."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.db import db_connection, in_placeholders

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

    with db_connection(db_path, row_factory=sqlite3.Row) as conn:
        results: list[dict[str, Any]] = []

        # Use FTS5 to find candidate memo IDs (handles fuzzy/tokenized matching)
        matching_memo_ids = _find_matching_memo_ids(conn, safe_q)

        # LIKE pattern for partial/substring matching (case-insensitive in SQLite)
        like_pattern = f"%{q}%"

        if matching_memo_ids:
            # Use FTS5 candidates narrowed by LIKE for precise matching
            ph = in_placeholders(len(matching_memo_ids))

            title_rows = conn.execute(
                f"SELECT m.id AS memo_id, m.title AS memo_title FROM memos m WHERE m.id IN ({ph}) AND m.title LIKE ?",
                [*matching_memo_ids, like_pattern],
            ).fetchall()

            seg_rows = conn.execute(
                f"SELECT s.id AS segment_id, s.memo_id AS memo_id, "
                f"s.text AS segment_text, s.start_ms, s.end_ms, "
                f"m.title AS memo_title "
                f"FROM segments s "
                f"JOIN memos m ON m.id = s.memo_id "
                f"WHERE s.memo_id IN ({ph}) AND s.text LIKE ?",
                [*matching_memo_ids, like_pattern],
            ).fetchall()
        else:
            # FTS5 returned nothing — fallback to LIKE-only search for substring matching
            title_rows = conn.execute(
                "SELECT m.id AS memo_id, m.title AS memo_title FROM memos m WHERE m.title LIKE ?",
                [like_pattern],
            ).fetchall()

            seg_rows = conn.execute(
                "SELECT s.id AS segment_id, s.memo_id AS memo_id, "
                "s.text AS segment_text, s.start_ms, s.end_ms, "
                "m.title AS memo_title "
                "FROM segments s "
                "JOIN memos m ON m.id = s.memo_id "
                "WHERE s.text LIKE ?",
                [like_pattern],
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
