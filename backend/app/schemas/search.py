"""Search schemas for the search API."""

from __future__ import annotations

from pydantic import BaseModel


class SearchResult(BaseModel):
    memo_id: str
    memo_title: str
    match_type: str  # "title" or "segment"
    segment_id: str | None = None
    segment_text: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
