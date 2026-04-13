"""Job API endpoints – snapshot, events (SSE), cancel."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.schemas.jobs import CancelResponse, JobDetailResponse, JobListResponse
from app.services import jobs as job_service
from app.services.sse import get_sse_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])

_settings = get_settings()
DATA_DIR = _settings.data_dir


def _job_to_response(job: dict) -> JobDetailResponse:
    """Convert a job dict to a JobDetailResponse."""
    return JobDetailResponse(
        id=job["id"],
        memo_id=job["memo_id"],
        job_type=job["job_type"],
        status=job["status"],
        stage=job.get("stage"),
        progress=job.get("progress", 0.0),
        eta_seconds=job.get("eta_seconds"),
        device_used=job.get("device_used"),
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
        attempt_count=job.get("attempt_count", 1),
        created_at=job["created_at"],
        updated_at=job.get("updated_at"),
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
    )


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str) -> JobDetailResponse:
    """Return current job snapshot.

    VAL-JOB-004: Returns complete job state.
    """
    db_path = DATA_DIR / "nanoscribe.db"
    job = job_service.get_job(db_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.get("/memos/{memo_id}/jobs", response_model=JobListResponse)
async def get_memo_jobs(memo_id: str) -> JobListResponse:
    """Return all jobs for a memo, ordered by created_at descending.

    VAL-JOB-017: Job list endpoint returns jobs for a memo.
    """
    db_path = DATA_DIR / "nanoscribe.db"
    jobs = job_service.get_jobs_for_memo(db_path, memo_id)
    return JobListResponse(jobs=[_job_to_response(j) for j in jobs])


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint for real-time job progress.

    VAL-TRANS-002: SSE event stream delivers real-time job updates.
    VAL-TRANS-003: On reconnect, first event is current state (no replay).
    VAL-JOB-018: Progress updates throttled to ~1/second.
    """
    db_path = DATA_DIR / "nanoscribe.db"
    job = job_service.get_job(db_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    manager = get_sse_manager()
    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        """SSE subscriber callback — pushes events to the queue."""
        await event_queue.put(event)

    manager.subscribe(job_id, on_event)

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events for the client."""
        try:
            # Send initial state event (VAL-TRANS-003)
            initial_data = {
                "status": job["status"],
                "stage": job.get("stage"),
                "progress": job.get("progress", 0.0),
            }
            yield f"event: job.state\ndata: {json.dumps(initial_data)}\n\n"

            # Check if already terminal
            if job["status"] in ("completed", "failed", "cancelled"):
                terminal_event = {
                    "completed": "job.completed",
                    "failed": "job.failed",
                    "cancelled": "job.cancelled",
                }[job["status"]]
                yield f"event: {terminal_event}\ndata: {json.dumps({'status': job['status']})}\n\n"
                return

            # Stream live events
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    break

                event_type = event.get("event", "message")
                data = event.get("data", {})
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

                # Stop on terminal events
                if event_type in ("job.completed", "job.failed", "job.cancelled"):
                    break
        finally:
            manager.unsubscribe(job_id, on_event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/jobs/{job_id}/cancel", response_model=CancelResponse)
async def cancel_job(job_id: str) -> CancelResponse:
    """Cancel a running job.

    VAL-TRANS-004: Cancel transitions to cancelled state.
    VAL-TRANS-005: Cancel of terminal job returns 409.
    """
    db_path = DATA_DIR / "nanoscribe.db"
    job = job_service.get_job(db_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    from app.services.jobs import TERMINAL_STATES

    if job["status"] in TERMINAL_STATES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel job in '{job['status']}' state",
        )

    # Signal the worker to stop processing this job
    from app.services.worker import get_worker

    worker = get_worker()
    if worker:
        worker.request_cancel(job_id)

    # Update DB immediately
    job_service.cancel_job(db_path, job_id)
    get_sse_manager().publish_cancelled(job_id)

    return CancelResponse(status="cancelled", message=f"Job {job_id} cancelled")


@router.post("/memos/{memo_id}/retry", response_model=JobDetailResponse)
async def retry_memo(memo_id: str) -> JobDetailResponse:
    """Retry a failed or cancelled memo's transcription.

    VAL-TRANS-007: Creates new job with incremented attempt_count.
    VAL-TRANS-008: Retry of active memo returns 409.
    """
    db_path = DATA_DIR / "nanoscribe.db"

    # Check that memo exists
    from app.db import get_connection

    conn = get_connection(db_path)
    try:
        memo = conn.execute("SELECT id, status FROM memos WHERE id = ?", (memo_id,)).fetchone()
    finally:
        conn.close()

    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    # Check latest job status
    latest_job = job_service.get_jobs_for_memo(db_path, memo_id)
    if latest_job:
        latest_status = latest_job[0]["status"]
        from app.services.jobs import ACTIVE_STATES

        if latest_status in ACTIVE_STATES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot retry: memo has active job in '{latest_status}' state",
            )

    new_job = job_service.retry_memo(db_path, memo_id)
    if new_job is None:
        raise HTTPException(
            status_code=409,
            detail="Cannot retry: memo does not have a failed or cancelled job",
        )

    return _job_to_response(new_job)


@router.post("/memos/{memo_id}/reprocess", response_model=JobDetailResponse, status_code=201)
async def reprocess_memo(memo_id: str, confirm: bool = False) -> JobDetailResponse:
    """Reprocess a memo's transcription — creates a new transcription job.

    Unlike retry (which only works on failed/cancelled jobs), reprocess works
    on completed memos too. This allows re-transcription with updated settings.

    If the transcript has been edited (transcript_revision > 1), the caller
    must pass confirm=true to acknowledge that edits will be overwritten.
    Without confirmation, returns 409.
    """
    db_path = DATA_DIR / "nanoscribe.db"

    # Check that memo exists
    from app.db import get_connection

    conn = get_connection(db_path)
    try:
        memo = conn.execute(
            "SELECT id, status, transcript_revision FROM memos WHERE id = ?",
            (memo_id,),
        ).fetchone()
    finally:
        conn.close()

    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    transcript_revision = memo[2]

    # Guard: if transcript has been edited, require confirmation
    if transcript_revision > 1 and not confirm:
        raise HTTPException(
            status_code=409,
            detail=f"Transcript has been edited (revision {transcript_revision}). "
            "Pass confirm=true to acknowledge that edits will be overwritten.",
        )

    # Check latest job status
    latest_jobs = job_service.get_jobs_for_memo(db_path, memo_id)
    if latest_jobs:
        latest_status = latest_jobs[0]["status"]
        from app.services.jobs import ACTIVE_STATES

        if latest_status in ACTIVE_STATES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot reprocess: memo has active job in '{latest_status}' state",
            )

    new_job = job_service.reprocess_memo(db_path, memo_id)
    if new_job is None:
        raise HTTPException(
            status_code=409,
            detail="Cannot reprocess: memo has no existing jobs",
        )

    return _job_to_response(new_job)
