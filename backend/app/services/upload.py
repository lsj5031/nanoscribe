"""Upload service – creates memos, jobs, and stores original files."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import get_settings
from app.db import get_connection

DATA_DIR = get_settings().data_dir

SUPPORTED_EXTENSIONS = frozenset(["wav", "mp3", "m4a", "aac", "webm", "ogg", "opus"])


def _title_from_filename(filename: str) -> str:
    """Derive default title from filename by removing the last extension.

    'interview-2026-04-13.mp3' → 'interview-2026-04-13'
    'file.with.dots.ogg' → 'file.with.dots'
    """
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    return name


def _is_supported_extension(filename: str) -> bool:
    """Check if the file extension is a supported audio format."""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def create_memo_and_job(
    filename: str,
    file_content: bytes,
    title: str | None = None,
    source_kind: str = "upload",
    language: str | None = None,
    enable_diarization: bool = False,
    hotwords: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Create a memo row, a job row, and store the original file.

    Returns {"memo": {...}, "job": {...}} on success.
    """
    memo_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    now = _now_iso()
    memo_title = title or _title_from_filename(filename)
    memo_dir = DATA_DIR / "memos" / memo_id

    # Store original file
    memo_dir.mkdir(parents=True, exist_ok=True)
    source_path = memo_dir / "source.original"
    source_path.write_bytes(file_content)

    db_path = DATA_DIR / "nanoscribe.db"
    conn = get_connection(db_path)
    try:
        # Insert memo
        conn.execute(
            """
            INSERT INTO memos
                (id, title, source_kind, source_filename,
                 status, language_override, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (memo_id, memo_title, source_kind, filename, language, now, now),
        )

        # Insert job
        conn.execute(
            """
            INSERT INTO jobs
                (id, memo_id, job_type, status, progress,
                 attempt_count, hotwords, enable_diarization, created_at)
            VALUES (?, ?, 'transcribe', 'queued', 0.0, 1, ?, ?, ?)
            """,
            (job_id, memo_id, hotwords, enable_diarization, now),
        )

        conn.commit()
    finally:
        conn.close()

    return {
        "memo": {
            "id": memo_id,
            "title": memo_title,
            "source_kind": source_kind,
            "source_filename": filename,
            "duration_ms": None,
            "language_detected": None,
            "language_override": language,
            "status": "queued",
            "speaker_count": 0,
            "transcript_revision": 0,
            "created_at": now,
            "updated_at": now,
        },
        "job": {
            "id": job_id,
            "memo_id": memo_id,
            "job_type": "transcribe",
            "status": "queued",
            "stage": None,
            "progress": 0.0,
            "eta_seconds": None,
            "device_used": None,
            "error_code": None,
            "error_message": None,
            "attempt_count": 1,
            "hotwords": hotwords,
            "enable_diarization": enable_diarization,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
        },
    }
