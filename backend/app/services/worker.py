"""Worker loop — processes one GPU transcription job at a time.

VAL-JOB-005: Only one GPU job runs at a time.
VAL-JOB-016: Startup recovery of stale jobs.
VAL-JOB-018: Progress updates throttled.

The worker runs as an asyncio background task. It polls the database for
queued jobs and processes them sequentially through the full pipeline:
  queued → preprocessing → transcribing → diarizing → finalizing → completed
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import get_settings
from app.services import jobs as job_service
from app.services.normalization import (
    NormalizationError,
    extract_duration_ms,
    extract_waveform_peaks,
    normalize_audio,
)
from app.services.sse import get_sse_manager
from app.services.transcription import TranscriptionError, persist_transcript

logger = logging.getLogger(__name__)

# Polling interval for checking queued jobs
POLL_INTERVAL_SECONDS = 2.0

# Cancellation check interval within a job
CANCEL_CHECK_INTERVAL = 0.5


class WorkerLoop:
    """Sequential job processor that runs one GPU task at a time.

    Usage:
        worker = WorkerLoop(db_path)
        asyncio.create_task(worker.run())
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._running = False
        self._current_job_id: str | None = None
        self._cancelled: set[str] = set()  # Set of cancelled job IDs

    @property
    def is_running(self) -> bool:
        return self._running

    def request_cancel(self, job_id: str) -> None:
        """Request cancellation of a job.

        The worker checks this set periodically during processing.
        """
        self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        """Check if a job has been requested to cancel."""
        return job_id in self._cancelled

    async def run(self) -> None:
        """Main worker loop. Polls for queued jobs and processes them."""
        self._running = True
        logger.info("Worker loop started")

        try:
            while self._running:
                try:
                    await self._process_next_job()
                except Exception as exc:
                    logger.error("Worker error: %s", exc, exc_info=True)

                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finally:
            self._running = False
            logger.info("Worker loop stopped")

    async def _process_next_job(self) -> None:
        """Pick up and process the next queued job, if any."""
        next_job = job_service.get_next_queued_job(self.db_path)
        if next_job is None:
            return

        job_id = next_job["id"]
        memo_id = next_job["memo_id"]
        self._current_job_id = job_id

        logger.info("Processing job %s for memo %s", job_id, memo_id)

        try:
            await self._run_pipeline(job_id, memo_id, next_job)
        except Exception as exc:
            logger.error("Pipeline failed for job %s: %s", job_id, exc, exc_info=True)
            job_service.fail_job(self.db_path, job_id, "UNKNOWN", str(exc))
            get_sse_manager().publish_failed(job_id, "UNKNOWN", str(exc))
        finally:
            self._current_job_id = None
            self._cancelled.discard(job_id)

    async def _run_pipeline(self, job_id: str, memo_id: str, job: dict) -> None:
        """Execute the full processing pipeline for a job."""
        sse = get_sse_manager()
        data_dir = get_settings().data_dir
        memo_dir = data_dir / "memos" / memo_id

        # ── Stage 1: Preprocessing ──────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "preprocessing")
        sse.publish_stage(job_id, "preprocessing")
        job_service.update_progress(self.db_path, job_id, 0.05)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        source_path = memo_dir / "source.original"
        if not source_path.exists():
            job_service.fail_job(self.db_path, job_id, "NORMALIZATION_FAILED", "Source file not found")
            sse.publish_failed(job_id, "NORMALIZATION_FAILED", "Source file not found")
            return

        try:
            normalized_path = normalize_audio(source_path, memo_dir)
        except NormalizationError as exc:
            job_service.fail_job(self.db_path, job_id, "NORMALIZATION_FAILED", str(exc))
            sse.publish_failed(job_id, "NORMALIZATION_FAILED", str(exc))
            return

        # Extract duration
        try:
            duration_ms = extract_duration_ms(normalized_path)
            conn = self._get_conn()
            try:
                conn.execute("UPDATE memos SET duration_ms = ? WHERE id = ?", (duration_ms, memo_id))
                conn.commit()
            finally:
                conn.close()
        except NormalizationError:
            pass  # Non-fatal — duration is informational

        # Extract waveform
        try:
            extract_waveform_peaks(normalized_path, memo_dir)
            sse.publish(job_id, {"event": "waveform.ready", "data": {"memo_id": memo_id}})
        except NormalizationError:
            pass  # Non-fatal

        job_service.update_progress(self.db_path, job_id, 0.1)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 2: Transcribing ───────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "transcribing")
        sse.publish_stage(job_id, "transcribing")

        hotwords = job.get("hotwords")

        try:
            from app.services.transcription import get_models

            models = get_models()
            result = await asyncio.to_thread(models.transcribe, normalized_path, hotwords=hotwords)
        except TranscriptionError as exc:
            job_service.fail_job(self.db_path, job_id, "ASR_FAILED", str(exc))
            sse.publish_failed(job_id, "ASR_FAILED", str(exc))
            return
        except Exception as exc:
            job_service.fail_job(self.db_path, job_id, "ASR_FAILED", str(exc))
            sse.publish_failed(job_id, "ASR_FAILED", str(exc))
            return

        # Report progress during transcription (simulated since FunASR is batch)
        job_service.update_progress(self.db_path, job_id, 0.7)
        sse.publish_progress(job_id, 0.7, "transcribing")

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 2b: Diarization (optional) ────────────────────────
        enable_diarization = bool(job.get("enable_diarization"))
        if enable_diarization:
            job_service.transition_job(self.db_path, job_id, "diarizing")
            sse.publish_stage(job_id, "diarizing")
            job_service.update_progress(self.db_path, job_id, 0.75)

            try:
                from app.services.diarization import run_diarization
                from app.services.diarization_merge import merge_diarization

                diarization_segments = await asyncio.to_thread(run_diarization, normalized_path)

                if diarization_segments:
                    result["segments"] = merge_diarization(result["segments"], diarization_segments)

                job_service.update_progress(self.db_path, job_id, 0.85)
                sse.publish_progress(job_id, 0.85, "diarizing")
            except Exception as exc:
                logger.warning("Diarization failed for job %s, continuing without speakers: %s", job_id, exc)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 3: Finalizing ─────────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "finalizing")
        sse.publish_stage(job_id, "finalizing")
        job_service.update_progress(self.db_path, job_id, 0.9)

        # Persist transcript
        try:
            await asyncio.to_thread(
                persist_transcript,
                memo_id,
                result["raw_output"],
                result["segments"],
                self.db_path,
            )
        except Exception as exc:
            job_service.fail_job(self.db_path, job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            sse.publish_failed(job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            return

        # Create speaker rows if diarization was applied
        if enable_diarization:
            try:
                from app.services.diarization import create_speaker_rows

                await asyncio.to_thread(create_speaker_rows, self.db_path, memo_id, result["segments"])
            except Exception as exc:
                logger.warning("Failed to create speaker rows for job %s: %s", job_id, exc)

        job_service.update_progress(self.db_path, job_id, 0.95)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 4: Completed ──────────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "completed")
        sse.publish_completed(job_id)
        logger.info("Job %s completed successfully", job_id)

    def _do_cancel(self, job_id: str) -> None:
        """Execute cancellation for a job."""
        job_service.cancel_job(self.db_path, job_id)
        get_sse_manager().publish_cancelled(job_id)
        logger.info("Job %s cancelled", job_id)

    def _get_conn(self):
        """Get a database connection."""
        from app.db import get_connection

        return get_connection(self.db_path)

    def stop(self) -> None:
        """Signal the worker to stop after current job completes."""
        self._running = False


# Module-level singleton
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
