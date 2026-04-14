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


class SegmentUpdate(BaseModel):
    """A single segment text update."""

    segment_id: str
    text: str


class PatchSegmentsRequest(BaseModel):
    """Request body for PATCH /api/memos/{memoId}/segments."""

    base_revision: int
    updates: list[SegmentUpdate]


class PatchSegmentsResponse(BaseModel):
    """Response for PATCH /api/memos/{memoId}/segments."""

    memo_id: str
    revision: int
    updated_segments: list[SegmentItem]


class ConflictResponse(BaseModel):
    """Response for 409 conflict."""

    detail: str
    current_revision: int
    current_segments: list[SegmentItem]
