"""Transcript persistence — write raw/final transcripts to disk and SQLite.

VAL-TRANS-010: Segments persisted to database and transcript JSON.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_settings = get_settings()
DATA_DIR = _settings.data_dir


def persist_transcript(
    memo_id: str,
    raw_output: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    db_path: Path,
) -> None:
    """Persist raw and final transcripts to filesystem and segments to SQLite.

    Writes:
      - transcript.raw.json: Raw ASR output
      - transcript.final.json: Editor-ready segment data
      - segments table rows in SQLite
    """
    from app.db import db_connection

    memo_dir = DATA_DIR / "memos" / memo_id

    raw_path = memo_dir / "transcript.raw.json"
    raw_path.write_text(json.dumps(raw_output, default=str, ensure_ascii=False, indent=2))

    final_segments = []
    for i, seg in enumerate(segments):
        final_segments.append(
            {
                "ordinal": i + 1,
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "text": seg["text"],
                "confidence": seg["confidence"],
                "speaker_key": seg.get("speaker_key"),
            }
        )

    final_path = memo_dir / "transcript.final.json"
    final_path.write_text(json.dumps(final_segments, ensure_ascii=False, indent=2))

    with db_connection(db_path) as conn:
        conn.execute("DELETE FROM segments WHERE memo_id = ?", (memo_id,))

        now = _now_iso()
        for i, seg in enumerate(segments):
            seg_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO segments
                    (id, memo_id, ordinal, start_ms, end_ms, text,
                     speaker_key, confidence, edited, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    seg_id,
                    memo_id,
                    i + 1,
                    seg["start_ms"],
                    seg["end_ms"],
                    seg["text"],
                    seg.get("speaker_key"),
                    seg["confidence"],
                    now,
                    now,
                ),
            )

        conn.execute(
            """
            UPDATE memos
            SET status = 'completed',
                transcript_revision = 1,
                speaker_count = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, memo_id),
        )

        conn.commit()

    logger.info("transcript_persisted", segment_count=len(segments), memo_id=memo_id)
