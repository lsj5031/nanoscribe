"""Export service – generate TXT, JSON, and SRT exports from transcript segments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms_to_srt_timestamp(ms: int) -> str:
    """Convert milliseconds to SRT timestamp format HH:MM:SS,mmm."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _ms_to_mm_ss(ms: int) -> str:
    """Convert milliseconds to MM:SS format for plain text export."""
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _get_export_data(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Fetch memo metadata, segments, and speakers for export.

    Returns None if memo not found.
    Returns {"memo": ..., "segments": [...], "speakers": {...}} otherwise.
    """
    conn = get_connection(db_path)
    try:
        memo = conn.execute(
            "SELECT id, title, duration_ms, transcript_revision FROM memos WHERE id = ?",
            (memo_id,),
        ).fetchone()
        if memo is None:
            return None

        memo_data = {
            "id": memo[0],
            "title": memo[1],
            "duration_ms": memo[2],
            "transcript_revision": memo[3],
        }

        rows = conn.execute(
            "SELECT id, ordinal, start_ms, end_ms, text, speaker_key FROM segments WHERE memo_id = ? ORDER BY ordinal",
            (memo_id,),
        ).fetchall()

        segments = [
            {
                "id": row[0],
                "ordinal": row[1],
                "start_ms": row[2],
                "end_ms": row[3],
                "text": row[4],
                "speaker_key": row[5],
            }
            for row in rows
        ]

        # Fetch speaker display names
        speaker_rows = conn.execute(
            "SELECT speaker_key, display_name FROM memo_speakers WHERE memo_id = ?",
            (memo_id,),
        ).fetchall()
        speakers = {row[0]: row[1] for row in speaker_rows}

        return {
            "memo": memo_data,
            "segments": segments,
            "speakers": speakers,
        }
    finally:
        conn.close()


def export_txt(db_path: str | Path, memo_id: str) -> tuple[str, str] | None:
    """Generate plain text export.

    Returns (content, filename) or None if memo not found.
    Raises ValueError if memo has no segments.
    """
    data = _get_export_data(db_path, memo_id)
    if data is None:
        return None

    segments = data["segments"]
    if not segments:
        raise ValueError("Memo has no segments")

    speakers = data["speakers"]
    title = data["memo"]["title"]
    lines: list[str] = []

    for seg in segments:
        timestamp = _ms_to_mm_ss(seg["start_ms"])
        speaker_name = speakers.get(seg["speaker_key"], seg["speaker_key"]) if seg["speaker_key"] else None
        text = seg["text"]

        if speaker_name:
            lines.append(f"{speaker_name} ({timestamp}):")
        else:
            lines.append(f"({timestamp}):")
        lines.append(text)
        lines.append("")

    content = "\n".join(lines).rstrip("\n") + "\n"
    filename = f"{title}.txt"
    return content, filename


def export_json(db_path: str | Path, memo_id: str) -> tuple[str, str] | None:
    """Generate structured JSON export.

    Returns (content, filename) or None if memo not found.
    Raises ValueError if memo has no segments.
    """
    data = _get_export_data(db_path, memo_id)
    if data is None:
        return None

    segments = data["segments"]
    if not segments:
        raise ValueError("Memo has no segments")

    speakers = data["speakers"]
    memo = data["memo"]

    export_data = {
        "memo_id": memo["id"],
        "title": memo["title"],
        "duration_ms": memo["duration_ms"],
        "exported_at": _now_iso(),
        "segments": [
            {
                "ordinal": seg["ordinal"],
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "speaker_key": seg["speaker_key"],
                "speaker_name": speakers.get(seg["speaker_key"], seg["speaker_key"]) if seg["speaker_key"] else None,
                "text": seg["text"],
            }
            for seg in segments
        ],
    }

    content = json.dumps(export_data, indent=2, ensure_ascii=False)
    filename = f"{memo['title']}.json"
    return content, filename


def export_srt(db_path: str | Path, memo_id: str) -> tuple[str, str] | None:
    """Generate SRT subtitle export.

    Returns (content, filename) or None if memo not found.
    Raises ValueError if memo has no segments.
    """
    data = _get_export_data(db_path, memo_id)
    if data is None:
        return None

    segments = data["segments"]
    if not segments:
        raise ValueError("Memo has no segments")

    speakers = data["speakers"]
    title = data["memo"]["title"]
    lines: list[str] = []

    for idx, seg in enumerate(segments, start=1):
        start_ts = _ms_to_srt_timestamp(seg["start_ms"])
        end_ts = _ms_to_srt_timestamp(seg["end_ms"])
        speaker_name = speakers.get(seg["speaker_key"], seg["speaker_key"]) if seg["speaker_key"] else None
        text = seg["text"]

        lines.append(str(idx))
        lines.append(f"{start_ts} --> {end_ts}")
        if speaker_name:
            lines.append(f"{speaker_name}: {text}")
        else:
            lines.append(text)
        lines.append("")

    content = "\n".join(lines).rstrip("\n") + "\n"
    filename = f"{title}.srt"
    return content, filename
