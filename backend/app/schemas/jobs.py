"""Pydantic schemas for job-related endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class JobDetailResponse(BaseModel):
    """Response schema for GET /api/jobs/{id}.

    VAL-JOB-004: Returns complete job state with all fields.
    """

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
    created_at: str
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class JobListResponse(BaseModel):
    """Response schema for GET /api/memos/{id}/jobs."""

    jobs: list[JobDetailResponse]


class CancelResponse(BaseModel):
    """Response schema for POST /api/jobs/{id}/cancel."""

    status: str
    message: str


class RetryResponse(BaseModel):
    """Response schema for POST /api/memos/{id}/retry."""

    job: JobDetailResponse
