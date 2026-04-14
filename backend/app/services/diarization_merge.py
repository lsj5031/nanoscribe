"""Merge diarization results with ASR segments."""

from __future__ import annotations

from typing import Any


def merge_diarization(
    asr_segments: list[dict[str, Any]],
    diarization_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign speaker_key to each ASR segment by greatest temporal overlap.

    For each ASR segment, finds the diarization speaker with the most
    temporal overlap and assigns that speaker_key.
    """
    if not diarization_segments:
        return asr_segments

    for seg in asr_segments:
        best_speaker: str | None = None
        best_overlap = 0

        seg_start = seg["start_ms"]
        seg_end = seg["end_ms"]

        for dseg in diarization_segments:
            overlap_start = max(seg_start, dseg["start_ms"])
            overlap_end = min(seg_end, dseg["end_ms"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = dseg["speaker"]

        seg["speaker_key"] = best_speaker

    return asr_segments
