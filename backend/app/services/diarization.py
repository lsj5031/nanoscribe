"""Diarization service using 3D-Speaker CAM++ model."""

from __future__ import annotations

import logging
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pastel colors for visual differentiation of speakers
SPEAKER_COLORS = [
    "#00d4ff",
    "#f472b6",
    "#a78bfa",
    "#34d399",
    "#fbbf24",
    "#fb923c",
]


def run_diarization(audio_path: Path) -> list[dict[str, Any]]:
    """Run speaker diarization on an audio file.

    Returns list of {"speaker": "spk0", "start_ms": 0, "end_ms": 5000}.

    Gracefully degrades if 3D-Speaker is not installed.
    """
    try:
        # Ensure 3D-Speaker is importable
        import speakerlab  # noqa: F401
    except ImportError:
        try:
            # Add /opt/3D-Speaker to path if installed via git clone
            sys.path.insert(0, "/opt/3D-Speaker")
            import speakerlab  # noqa: F401
        except ImportError:
            logger.warning(
                "3D-Speaker not installed — skipping diarization. "
                "Install via: git clone https://github.com/modelscope/3D-Speaker /opt/3D-Speaker"
            )
            return []

    try:
        import torch
        from speakerlab.bin.infer_diarization import Diarization3Dspeaker

        device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        diarization = Diarization3Dspeaker(device=device)

        # Diarization3Dspeaker.__call__ returns [[start_s, end_s, speaker_id], ...]
        raw_result = diarization(str(audio_path))

        segments: list[dict[str, Any]] = []
        for seg in raw_result:
            start_s, end_s, speaker_id = seg[0], seg[1], seg[2]
            segments.append(
                {
                    "speaker": f"spk{speaker_id}",
                    "start_ms": int(round(start_s * 1000)),
                    "end_ms": int(round(end_s * 1000)),
                }
            )
        return segments
    except Exception:
        logger.exception("Diarization failed")
        return []


def create_speaker_rows(db_path: Path, memo_id: str, segments: list[dict[str, Any]]) -> None:
    """Create memo_speakers rows from diarized segments.

    For each unique speaker_key in the segments, creates a memo_speakers row
    with a default label (Speaker 1, Speaker 2, etc.) and a pastel color.
    Also updates the memo's speaker_count.
    """
    # Find unique speakers in order of first appearance
    seen: set[str] = set()
    speakers: list[str] = []
    for seg in segments:
        spk = seg.get("speaker_key")
        if spk and spk not in seen:
            seen.add(spk)
            speakers.append(spk)

    if not speakers:
        return

    conn = sqlite3.connect(str(db_path))
    try:
        for i, spk in enumerate(speakers):
            color = SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
            display_name = f"Speaker {i + 1}"
            speaker_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                (speaker_id, memo_id, spk, display_name, color),
            )
        # Update memo speaker_count
        conn.execute(
            "UPDATE memos SET speaker_count = ? WHERE id = ?",
            (len(speakers), memo_id),
        )
        conn.commit()
    finally:
        conn.close()
