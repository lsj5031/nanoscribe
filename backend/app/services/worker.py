"""Worker loop — processes one GPU transcription job at a time.

VAL-JOB-005: Only one GPU job runs at a time.
VAL-JOB-016: Startup recovery of stale jobs.
VAL-JOB-018: Progress updates throttled.

The worker runs as an asyncio background task. It polls the database for
queued jobs and processes them sequentially using a configurable pipeline
of Stage adapters (see ``app.services.pipeline``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.config import get_settings
from app.services import jobs as job_service
from app.services.pipeline import (
    PipelineContext,
    build_diarize_pipeline,
    build_transcribe_pipeline,
)
from app.services.protocols import TranscriptionError
from app.services.sse import get_sse_manager

logger = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 2.0

_job_available: asyncio.Event | None = None


def notify_job_queued() -> None:
    """Signal the worker that a new job is available."""
    if _job_available is not None:
        _job_available.set()


class WorkerLoop:
    """Sequential job processor that runs one GPU task at a time."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._running = False
        self._current_job_id: str | None = None
        self._cancelled: set[str] = set()

    @property
    def is_running(self) -> bool:
        return self._running

    def request_cancel(self, job_id: str) -> None:
        self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    async def run(self) -> None:
        """Main worker loop. Polls for queued jobs and processes them."""
        global _job_available
        self._running = True
        _job_available = asyncio.Event()
        logger.info("worker_loop_started")

        try:
            while self._running:
                try:
                    await self._process_next_job()
                except Exception as exc:
                    logger.error("worker_loop_error", error=str(exc), exc_info=True)

                try:
                    await asyncio.wait_for(_job_available.wait(), timeout=POLL_INTERVAL_SECONDS)
                    _job_available.clear()
                except asyncio.TimeoutError:
                    pass
        finally:
            self._running = False
            _job_available = None
            logger.info("worker_loop_stopped")

    async def _process_next_job(self) -> None:
        """Pick up and process the next queued job, if any."""
        next_job = job_service.get_next_queued_job(self.db_path)
        if next_job is None:
            return

        job_id = next_job["id"]
        memo_id = next_job["memo_id"]
        self._current_job_id = job_id

        clear_contextvars()
        bind_contextvars(job_id=job_id, memo_id=memo_id)

        logger.info("job_picked", attempt_count=next_job.get("attempt_count"))

        try:
            job_type = next_job.get("job_type", "transcribe")
            data_dir = get_settings().data_dir

            ctx = PipelineContext(
                job_id=job_id,
                memo_id=memo_id,
                db_path=self.db_path,
                data_dir=data_dir,
                job_type=job_type,
                hotwords=next_job.get("hotwords"),
                enable_diarization=bool(next_job.get("enable_diarization")),
            )

            sse = get_sse_manager()

            if job_type == "diarize":
                pipeline = build_diarize_pipeline()
            else:
                pipeline = build_transcribe_pipeline()

            success = await pipeline.run(ctx, sse, lambda: self.is_cancelled(job_id))

            if ctx.cancelled:
                self._do_cancel(job_id)
            elif not success:
                pass  # Stage already reported failure via fail_job + SSE
        except TranscriptionError as exc:
            logger.error("pipeline_failed", error=str(exc))
            job_service.fail_job(self.db_path, job_id, "ASR_FAILED", str(exc))
            get_sse_manager().publish_failed(job_id, "ASR_FAILED", str(exc))
        except Exception as exc:
            logger.error("pipeline_failed", error=str(exc), exc_info=True)
            job_service.fail_job(self.db_path, job_id, "UNKNOWN", str(exc))
            get_sse_manager().publish_failed(job_id, "UNKNOWN", str(exc))
        finally:
            self._current_job_id = None
            self._cancelled.discard(job_id)
            clear_contextvars()

    def _do_cancel(self, job_id: str) -> None:
        """Execute cancellation for a job."""
        job_service.cancel_job(self.db_path, job_id)
        get_sse_manager().publish_cancelled(job_id)
        logger.info("job_cancelled")

    def stop(self) -> None:
        """Signal the worker to stop after current job completes."""
        self._running = False


_worker: WorkerLoop | None = None


async def start_worker(db_path: Path) -> WorkerLoop:
    """Start the worker loop as a background task."""
    global _worker
    if _worker is not None and _worker.is_running:
        return _worker

    _worker = WorkerLoop(db_path)
    asyncio.create_task(_worker.run())
    return _worker


def get_worker() -> WorkerLoop | None:
    """Return the current worker instance, if any."""
    return _worker
