"""Pydantic schemas for memo/job upload endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class MemoResponse(BaseModel):
    """Response schema for a memo row."""

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


class JobResponse(BaseModel):
    """Response schema for a job row."""

    id: str
    memo_id: str
    job_type: str
    status: str
    stage: str | None = None
    progress: float = 0.0
    eta_seconds: float | None = None
    device_used: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int = 1
    hotwords: str | None = None
    enable_diarization: bool = False
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class FileError(BaseModel):
    """Error info for a single file in a batch upload."""

    filename: str
    error: str


class UploadResponse(BaseModel):
    """Response schema for POST /api/memos."""

    memos: list[MemoResponse]
    jobs: list[JobResponse]
    errors: list[FileError] = []
