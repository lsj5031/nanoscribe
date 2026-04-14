"""Pydantic schemas for speaker-related endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Hex color regex: #RRGGBB
_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class SpeakerItem(BaseModel):
    """A single memo-local speaker."""

    id: str
    speaker_key: str
    display_name: str
    color: str


class SpeakersResponse(BaseModel):
    """Response for GET /api/memos/{memoId}/speakers."""

    memo_id: str
    speakers: list[SpeakerItem]


class SpeakerUpdate(BaseModel):
    """A single speaker update (display_name and/or color)."""

    speaker_key: str
    display_name: str = Field(max_length=50)
    color: str = Field(pattern=_HEX_COLOR)


class PatchSpeakersRequest(BaseModel):
    """Request body for PATCH /api/memos/{memoId}/speakers."""

    updates: list[SpeakerUpdate]


class PatchSpeakersResponse(BaseModel):
    """Response for PATCH /api/memos/{memoId}/speakers."""

    memo_id: str
    speakers: list[SpeakerItem]
