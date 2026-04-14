"""Pydantic schemas for segment endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class SegmentItem(BaseModel):
    """A single transcript segment."""

    id: str
    ordinal: int
    start_ms: int
    end_ms: int
    text: str
    speaker_key: str | None = None
    confidence: float | None = None
    edited: bool = False


class SegmentsResponse(BaseModel):
    """Response for GET /api/memos/{memoId}/segments."""

    memo_id: str
    revision: int
    segments: list[SegmentItem]
