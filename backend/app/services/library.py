"""Library service – list, detail, delete memos with FTS5 search sync.

Handles VAL-LIB-xxx assertions:
  - Paginated memo listing with search, sort, filters (VAL-LIB-001)
  - FTS5 search across titles and segments (VAL-LIB-002)
  - Sort by recent / duration (VAL-LIB-003/004)
  - Filter by status / language (VAL-LIB-005/006)
  - Memo detail with job summary and export availability (VAL-LIB-016)
  - Delete memo with all artifacts (VAL-LIB-014)
  - FTS5 index consistency on delete (VAL-SEARCH-015)
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from app.db import db_connection, in_placeholders

# Valid status values for filtering
VALID_STATUSES = frozenset(
    {
        "queued",
        "preprocessing",
        "transcribing",
        "diarizing",
        "finalizing",
        "completed",
        "failed",
        "cancelled",
    }
)

# Valid sort options
VALID_SORTS = frozenset({"recent", "duration"})

# Default pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def list_memos(
    db_path: str | Path,
    *,
    q: str | None = None,
    sort: str = "recent",
    status: str | None = None,
    language: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """List memos with pagination, search, sort, and filters.

    Returns {"items": [...], "total": N, "page": P, "page_size": PS}.
    """
    with db_connection(db_path, row_factory=sqlite3.Row) as conn:
        # Build query parts
        conditions: list[str] = []
        params: list[Any] = []

        # FTS5 search (VAL-LIB-002)
        if q and q.strip():
            # Escape FTS5 special characters
            safe_q = _escape_fts_query(q.strip())
            # Use a simpler approach: find memo IDs that match via FTS
            matching_ids = _find_matching_memo_ids(conn, safe_q)
            if matching_ids:
                ph = in_placeholders(len(matching_ids))
                conditions.append(f"memos.id IN ({ph})")
                params.extend(matching_ids)
            else:
                # No matches — return empty immediately
                return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # Status filter (VAL-LIB-005)
        if status and status.strip():
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            invalid = set(statuses) - VALID_STATUSES
            if invalid:
                raise ValueError(f"Invalid status value(s): {', '.join(sorted(invalid))}")
            ph = in_placeholders(len(statuses))
            conditions.append(f"memos.status IN ({ph})")
            params.extend(statuses)

        # Language filter (VAL-LIB-006)
        if language and language.strip():
            lang = language.strip()
            # language_override takes precedence; if set, filter on it;
            # if not set, filter on language_detected
            conditions.append("COALESCE(memos.language_override, memos.language_detected) = ?")
            params.append(lang)

        # Build WHERE clause
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Count total (VAL-LIB-017)
        count_sql = f"SELECT COUNT(*) FROM memos {where}"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Sort (VAL-LIB-003/004)
        if sort == "duration":
            order = "memos.duration_ms DESC, memos.updated_at DESC"
        else:  # "recent" or default
            order = "memos.updated_at DESC, memos.id DESC"

        # Paginate (VAL-LIB-017)
        offset = (page - 1) * page_size
        data_sql = (
            f"SELECT memos.id, memos.title, memos.duration_ms, memos.speaker_count, "
            f"memos.status, memos.updated_at, "
            f"j.progress AS job_progress, j.stage AS job_stage "
            f"FROM memos "
            f"LEFT JOIN ("
            f"  SELECT memo_id, progress, stage, "
            f"    ROW_NUMBER() OVER (PARTITION BY memo_id ORDER BY created_at DESC) AS rn "
            f"  FROM jobs"
            f") j ON j.memo_id = memos.id AND j.rn = 1 "
            f"{where} "
            f"ORDER BY {order} "
            f"LIMIT ? OFFSET ?"
        )
        rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

        items = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "duration_ms": row["duration_ms"],
                    "speaker_count": row["speaker_count"],
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                    "waveform_url": None,  # Will be populated by API layer if file exists
                    "progress": row["job_progress"] if row["job_progress"] is not None else 0.0,
                    "stage": row["job_stage"],
                }
            )

        return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_memo_detail(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Get full memo detail with job summary and export availability.

    VAL-LIB-016: Returns complete metadata with job summary and exports.
    Returns None if memo not found.
    """
    with db_connection(db_path, row_factory=sqlite3.Row) as conn:
        row = conn.execute(
            "SELECT * FROM memos WHERE id = ?",
            (memo_id,),
        ).fetchone()
        if row is None:
            return None

        memo = dict(row)

        # Latest job summary (VAL-LIB-016)
        job_row = conn.execute(
            "SELECT id, memo_id, job_type, status, stage, progress, "
            "error_code, error_message, attempt_count, created_at "
            "FROM jobs WHERE memo_id = ? ORDER BY created_at DESC LIMIT 1",
            (memo_id,),
        ).fetchone()

        memo["latest_job"] = dict(job_row) if job_row else None

        # Export availability — all formats can be generated on demand
        # once there are segments. For now, always available if job completed.
        memo["exports"] = {
            "txt": memo["status"] == "completed",
            "json": memo["status"] == "completed",
            "srt": memo["status"] == "completed",
        }

        return memo


def delete_memo(db_path: str | Path, data_dir: Path, memo_id: str) -> bool:
    """Delete a memo and all associated data.

    VAL-LIB-014: Removes memo, segments, speakers, jobs, filesystem artifacts.
    VAL-SEARCH-015: FTS5 index entries removed via CASCADE + triggers.
    Returns True if deleted, False if not found.
    """
    with db_connection(db_path) as conn:
        # Check existence
        exists = conn.execute("SELECT 1 FROM memos WHERE id = ?", (memo_id,)).fetchone()
        if not exists:
            return False

        # Delete segments first so segment FTS triggers fire correctly
        conn.execute("DELETE FROM segments WHERE memo_id = ?", (memo_id,))

        # Delete speakers
        conn.execute("DELETE FROM memo_speakers WHERE memo_id = ?", (memo_id,))

        # Delete jobs
        conn.execute("DELETE FROM jobs WHERE memo_id = ?", (memo_id,))

        # Now delete the memo (memo FTS trigger fires here)
        conn.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
        conn.commit()

    # Remove filesystem artifacts
    memo_dir = data_dir / "memos" / memo_id
    if memo_dir.exists():
        shutil.rmtree(memo_dir, ignore_errors=True)

    return True


def _escape_fts_query(q: str) -> str:
    """Escape FTS5 special characters in a search query.

    FTS5 uses " for phrases, * for prefix, AND/OR/NOT as operators.
    We wrap the query in quotes to treat it as a literal phrase.
    """
    # Escape double quotes within the query
    escaped = q.replace('"', '""')
    return f'"{escaped}"'


def _find_matching_memo_ids(conn: sqlite3.Connection, safe_q: str) -> list[str]:
    """Find memo IDs that match the FTS5 query in title or segment text.

    Returns a list of distinct memo IDs.
    """
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

    # Combine and deduplicate
    ids: set[str] = set()
    for (memo_id,) in title_matches:
        ids.add(memo_id)
    for (memo_id,) in seg_matches:
        ids.add(memo_id)

    return list(ids)
