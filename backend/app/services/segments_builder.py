"""Segment-building utilities — pure functions for transcript segment construction.

These functions are pure: no I/O, no state, no side effects.  They take
timestamps, VAD segments, or token data and return structured segment dicts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.protocols import _SENTENCE_END


def merge_vad_segments(
    vad_segments: list[list[int]],
    gap_threshold_ms: int = 800,
    max_duration_ms: int = 30_000,
) -> list[list[int]]:
    """Merge adjacent VAD segments that are close together.

    Merges segments whose gap is ≤ *gap_threshold_ms* unless the
    resulting chunk would exceed *max_duration_ms*.  This reduces
    the number of ASR calls while keeping each chunk small enough
    to avoid GPU OOM.
    """
    if not vad_segments:
        return []

    merged: list[list[int]] = [list(vad_segments[0])]

    for start, end in vad_segments[1:]:
        prev = merged[-1]
        gap = start - prev[1]
        duration_if_merged = end - prev[0]

        if gap <= gap_threshold_ms and duration_if_merged <= max_duration_ms:
            prev[1] = end
        else:
            merged.append([start, end])

    return merged


def extract_chunk(
    audio_path: str | Path,
    start_ms: int,
    end_ms: int,
    buffer_ms: int = 200,
    min_chunk_ms: int = 400,
) -> tuple[Path, int] | None:
    """Extract a chunk of audio as a temporary WAV file using ffmpeg.

    Pads the chunk by *buffer_ms* on each side to avoid clipping
    words at segment boundaries.  Returns ``(chunk_path, padded_start_ms)``
    or None if the chunk is too short.

    The caller must use *padded_start_ms* (not *start_ms*) as the offset
    when adjusting timestamps, because time 0 in the extracted WAV
    corresponds to *padded_start_ms* in the full audio.
    """
    import subprocess
    import tempfile

    audio_path = Path(audio_path)

    padded_start = max(0, start_ms - buffer_ms)
    padded_end = end_ms + buffer_ms
    chunk_duration_ms = padded_end - padded_start

    if chunk_duration_ms < min_chunk_ms:
        return None

    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav",
        prefix=f"chunk_{padded_start}_",
        delete=False,
    )
    tmp.close()
    chunk_path = Path(tmp.name)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{padded_start}ms",
        "-i",
        str(audio_path),
        "-t",
        f"{chunk_duration_ms}ms",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(chunk_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        try:
            chunk_path.unlink()
        except OSError:
            pass
        return None

    if result.returncode != 0 or not chunk_path.exists() or chunk_path.stat().st_size == 0:
        try:
            chunk_path.unlink()
        except OSError:
            pass
        return None

    return chunk_path, padded_start


def tokens_to_segment(tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Convert a list of token dicts to a segment dict.

    Returns None if the resulting segment would be empty.
    """
    if not tokens:
        return None

    text = "".join(t.get("token", "") for t in tokens).strip()
    if not text:
        return None

    start_s = tokens[0].get("start_time", 0)
    end_s = tokens[-1].get("end_time", 0)

    scores = [t.get("score", 0) for t in tokens if t.get("score", 0) > 0]
    confidence = sum(scores) / len(scores) if scores else 1.0

    return {
        "start_ms": int(round(start_s * 1000)),
        "end_ms": int(round(end_s * 1000)),
        "text": text,
        "confidence": round(confidence, 4),
    }


def build_segments_from_timestamps(
    timestamps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build segments from token-level timestamps.

    Each timestamp has: token, start_time (seconds), end_time (seconds), score (confidence).

    Groups tokens into sentence-level segments by splitting on sentence-ending
    punctuation. Each segment gets the start time of its first token and end time
    of its last token. Confidence is the average of token scores.
    """
    if not timestamps:
        return []

    segments: list[dict[str, Any]] = []
    current_tokens: list[dict[str, Any]] = []

    for ts in timestamps:
        current_tokens.append(ts)

        token = ts.get("token", "")
        if token in _SENTENCE_END and len(current_tokens) > 1:
            seg = tokens_to_segment(current_tokens)
            if seg:
                segments.append(seg)
            current_tokens = []

    if current_tokens:
        seg = tokens_to_segment(current_tokens)
        if seg:
            segments.append(seg)

    return segments


def build_segments_from_vad(
    vad_segments: list[list[int]],
    full_text: str,
) -> list[dict[str, Any]]:
    """Build segments from VAD timing when no token-level timestamps are available.

    Distributes the full text proportionally across VAD segments by character count.
    """
    if not vad_segments or not full_text:
        return []

    if len(vad_segments) == 1:
        return [
            {
                "start_ms": vad_segments[0][0],
                "end_ms": vad_segments[0][1],
                "text": full_text,
                "confidence": 1.0,
            }
        ]

    total_vad_ms = sum(end - start for start, end in vad_segments)
    if total_vad_ms <= 0:
        return [
            {
                "start_ms": vad_segments[0][0],
                "end_ms": vad_segments[-1][1],
                "text": full_text,
                "confidence": 1.0,
            }
        ]

    segments: list[dict[str, Any]] = []
    chars_per_ms = len(full_text) / total_vad_ms

    char_offset = 0
    for start_ms, end_ms in vad_segments:
        segment_ms = end_ms - start_ms
        n_chars = max(1, int(round(segment_ms * chars_per_ms)))
        n_chars = min(n_chars, len(full_text) - char_offset)

        if char_offset >= len(full_text):
            break

        seg_text = full_text[char_offset : char_offset + n_chars].strip()
        char_offset += n_chars

        if seg_text:
            segments.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": seg_text,
                    "confidence": 1.0,
                }
            )

    if char_offset < len(full_text) and segments:
        remaining = full_text[char_offset:].strip()
        if remaining:
            segments[-1]["text"] += " " + remaining

    return segments
