"""Pydantic schemas for library endpoints: list, detail, delete."""

from __future__ import annotations

from pydantic import BaseModel


class MemoCard(BaseModel):
    """Summary card for a memo in library listing.

    VAL-LIB-001: items contain id, title, duration_ms, speaker_count, status, updated_at.
    """

    id: str
    title: str
    duration_ms: int | None = None
    speaker_count: int = 0
    status: str
    updated_at: str
    waveform_url: str | None = None
    progress: float = 0.0
    stage: str | None = None


class JobSummary(BaseModel):
    """Summary of the latest job for a memo detail response."""

    id: str
    memo_id: str
    job_type: str
    status: str
    stage: str | None = None
    progress: float = 0.0
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int = 1
    created_at: str


class MemoDetail(BaseModel):
    """Full memo detail for GET /api/memos/{id}.

    VAL-LIB-016: Returns complete metadata with job summary and export availability.
    """

    id: str
    title: str
    source_kind: str
    source_filename: str
    duration_ms: int | None = None
    language_detected: str | None = None
    language_override: str | None = None
    status: str
    speaker_count: int = 0
    transcript_revision: int = 0
    created_at: str
    updated_at: str
    last_opened_at: str | None = None
    last_edited_at: str | None = None
    latest_job: JobSummary | None = None
    exports: dict[str, bool]


class PaginatedMemos(BaseModel):
    """Paginated response for GET /api/memos.

    VAL-LIB-001: Response includes items, total, page, page_size.
    """

    items: list[MemoCard]
    total: int
    page: int
    page_size: int
