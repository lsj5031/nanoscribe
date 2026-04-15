"""Worker loop — processes one GPU transcription job at a time.

VAL-JOB-005: Only one GPU job runs at a time.
VAL-JOB-016: Startup recovery of stale jobs.
VAL-JOB-018: Progress updates throttled.

The worker runs as an asyncio background task. It polls the database for
queued jobs and processes them sequentially through the full pipeline:
  queued → preprocessing → transcribing → diarizing → finalizing → completed

For ``job_type='diarize'`` jobs, the pipeline skips transcription and only
runs diarization on the already-transcribed memo.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

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

logger = structlog.get_logger(__name__)

# Polling interval for checking queued jobs
POLL_INTERVAL_SECONDS = 2.0

# Progress ranges for each stage (start, end)
# Transcription (0.10 → 0.65): granular per-chunk progress reported via callback
# Diarization (0.65 → 0.85): coarse progress
# Finalizing (0.85 → 0.95): quick
_PROGRESS_TRANSCRIBE_START = 0.10
_PROGRESS_TRANSCRIBE_END = 0.65
_PROGRESS_DIARIZE_START = 0.65
_PROGRESS_DIARIZE_END = 0.85
_PROGRESS_FINALIZE = 0.85
_PROGRESS_FINALIZE_END = 0.95


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
        logger.info("worker_loop_started")

        try:
            while self._running:
                try:
                    await self._process_next_job()
                except Exception as exc:
                    logger.error("worker_loop_error", error=str(exc), exc_info=True)

                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finally:
            self._running = False
            logger.info("worker_loop_stopped")

    async def _process_next_job(self) -> None:
        """Pick up and process the next queued job, if any."""
        next_job = job_service.get_next_queued_job(self.db_path)
        if next_job is None:
            return

        job_id = next_job["id"]
        memo_id = next_job["memo_id"]
        self._current_job_id = job_id

        # Bind job context so all subsequent log calls include job_id/memo_id
        clear_contextvars()
        bind_contextvars(job_id=job_id, memo_id=memo_id)

        logger.info("job_picked", attempt_count=next_job.get("attempt_count"))

        try:
            job_type = next_job.get("job_type", "transcribe")
            if job_type == "diarize":
                await self._run_diarize_pipeline(job_id, memo_id, next_job)
            else:
                await self._run_pipeline(job_id, memo_id, next_job)
        except Exception as exc:
            logger.error("pipeline_failed", error=str(exc), exc_info=True)
            job_service.fail_job(self.db_path, job_id, "UNKNOWN", str(exc))
            get_sse_manager().publish_failed(job_id, "UNKNOWN", str(exc))
        finally:
            self._current_job_id = None
            self._cancelled.discard(job_id)
            clear_contextvars()

    async def _run_pipeline(self, job_id: str, memo_id: str, job: dict) -> None:
        """Execute the full processing pipeline for a transcription job."""
        sse = get_sse_manager()
        data_dir = get_settings().data_dir
        memo_dir = data_dir / "memos" / memo_id

        # ── Stage 1: Preprocessing ──────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "preprocessing")
        sse.publish_stage(job_id, "preprocessing")
        job_service.update_progress(self.db_path, job_id, 0.05)
        logger.info("stage_started", stage="preprocessing")

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        source_path = memo_dir / "source.original"
        if not source_path.exists():
            logger.error("source_file_missing", path=str(source_path))
            job_service.fail_job(self.db_path, job_id, "NORMALIZATION_FAILED", "Source file not found")
            sse.publish_failed(job_id, "NORMALIZATION_FAILED", "Source file not found")
            return

        try:
            normalized_path = normalize_audio(source_path, memo_dir)
            logger.info("audio_normalized", output=str(normalized_path))
        except NormalizationError as exc:
            logger.error("normalization_failed", error=str(exc))
            job_service.fail_job(self.db_path, job_id, "NORMALIZATION_FAILED", str(exc))
            sse.publish_failed(job_id, "NORMALIZATION_FAILED", str(exc))
            return

        # Extract duration
        try:
            duration_ms = extract_duration_ms(normalized_path)
            with self._db_connection() as conn:
                conn.execute("UPDATE memos SET duration_ms = ? WHERE id = ?", (duration_ms, memo_id))
                conn.commit()
            logger.info("duration_extracted", duration_ms=duration_ms)
        except NormalizationError:
            logger.debug("duration_extraction_skipped")  # Non-fatal

        # Extract waveform
        try:
            extract_waveform_peaks(normalized_path, memo_dir)
            sse.publish(job_id, {"event": "waveform.ready", "data": {"memo_id": memo_id}})
            logger.info("waveform_extracted")
        except NormalizationError:
            logger.debug("waveform_extraction_skipped")  # Non-fatal

        job_service.update_progress(self.db_path, job_id, 0.1)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 2: Transcribing (with per-chunk progress) ──────────
        t_transcribe_start = time.monotonic()
        job_service.transition_job(self.db_path, job_id, "transcribing")
        sse.publish_stage(job_id, "transcribing")
        logger.info("stage_started", stage="transcribing")

        hotwords = job.get("hotwords")

        # Build a chunk callback that maps chunk progress to overall range
        # [0.10 .. 0.65] and publishes SSE from the thread.
        db_path = self.db_path

        def _chunk_callback(chunks_done: int, total_chunks: int) -> None:
            """Called from the transcription thread after each ASR chunk."""
            if total_chunks <= 0:
                return
            frac = chunks_done / total_chunks
            progress = _PROGRESS_TRANSCRIBE_START + frac * (_PROGRESS_TRANSCRIBE_END - _PROGRESS_TRANSCRIBE_START)
            # DB update is thread-safe (uses its own connection)
            job_service.update_progress(db_path, job_id, progress)
            # SSE must be dispatched to the main event loop
            sse.publish_progress_threadsafe(
                job_id,
                progress,
                stage="transcribing",
                detail={"chunks_done": chunks_done, "total_chunks": total_chunks},
            )

        try:
            from app.services.transcription import get_models

            models = get_models()
            result = await asyncio.to_thread(
                models.transcribe,
                normalized_path,
                hotwords=hotwords,
                chunk_callback=_chunk_callback,
            )
            t_transcribe_elapsed = time.monotonic() - t_transcribe_start
            segment_count = len(result.get("segments", []))
            logger.info(
                "transcription_completed",
                segment_count=segment_count,
                elapsed_s=round(t_transcribe_elapsed, 2),
            )
        except TranscriptionError as exc:
            logger.error("transcription_failed", error=str(exc))
            job_service.fail_job(self.db_path, job_id, "ASR_FAILED", str(exc))
            sse.publish_failed(job_id, "ASR_FAILED", str(exc))
            return
        except Exception as exc:
            logger.error("transcription_failed", error=str(exc), exc_info=True)
            job_service.fail_job(self.db_path, job_id, "ASR_FAILED", str(exc))
            sse.publish_failed(job_id, "ASR_FAILED", str(exc))
            return

        # Report progress at end of transcription stage
        job_service.update_progress(self.db_path, job_id, _PROGRESS_TRANSCRIBE_END)
        sse.publish_progress(job_id, _PROGRESS_TRANSCRIBE_END, "transcribing")

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 2b: Diarization ─────────────────────────────────────
        enable_diarization = bool(job.get("enable_diarization"))
        if enable_diarization:
            t_diarize_start = time.monotonic()
            job_service.transition_job(self.db_path, job_id, "diarizing")
            sse.publish_stage(job_id, "diarizing")
            job_service.update_progress(self.db_path, job_id, _PROGRESS_DIARIZE_START)
            logger.info("stage_started", stage="diarizing")

            try:
                from app.services.diarization import run_diarization
                from app.services.diarization_merge import merge_diarization

                diarization_segments = await asyncio.to_thread(run_diarization, normalized_path)

                if diarization_segments:
                    result["segments"] = merge_diarization(result["segments"], diarization_segments)
                    logger.info(
                        "diarization_completed",
                        speaker_segments=len(diarization_segments),
                        elapsed_s=round(time.monotonic() - t_diarize_start, 2),
                    )

                job_service.update_progress(self.db_path, job_id, _PROGRESS_DIARIZE_END)
                sse.publish_progress(job_id, _PROGRESS_DIARIZE_END, "diarizing")
            except Exception as exc:
                logger.warning("diarization_failed", error=str(exc))
        else:
            # No diarization — skip straight to finalizing range
            job_service.update_progress(self.db_path, job_id, _PROGRESS_DIARIZE_END)
            sse.publish_progress(job_id, _PROGRESS_DIARIZE_END)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 3: Finalizing ─────────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "finalizing")
        sse.publish_stage(job_id, "finalizing")
        job_service.update_progress(self.db_path, job_id, _PROGRESS_FINALIZE)
        logger.info("stage_started", stage="finalizing")

        # Persist transcript
        try:
            await asyncio.to_thread(
                persist_transcript,
                memo_id,
                result["raw_output"],
                result["segments"],
                self.db_path,
            )
            logger.info("transcript_persisted")
        except Exception as exc:
            logger.error("transcript_persist_failed", error=str(exc))
            job_service.fail_job(self.db_path, job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            sse.publish_failed(job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            return

        # Create speaker rows if diarization was applied
        if enable_diarization:
            try:
                from app.services.diarization import create_speaker_rows

                await asyncio.to_thread(create_speaker_rows, self.db_path, memo_id, result["segments"])
            except Exception as exc:
                logger.warning("speaker_rows_failed", error=str(exc))

        job_service.update_progress(self.db_path, job_id, _PROGRESS_FINALIZE_END)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 4: Completed ──────────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "completed")
        sse.publish_completed(job_id)
        logger.info("job_completed")

    async def _run_diarize_pipeline(self, job_id: str, memo_id: str, job: dict) -> None:
        """Execute a diarization-only pipeline for job_type='diarize'.

        Skips transcription. Loads the existing transcript, runs diarization,
        merges speaker labels, and persists the result.
        """
        import json

        sse = get_sse_manager()
        data_dir = get_settings().data_dir
        memo_dir = data_dir / "memos" / memo_id

        # ── Stage 1: Preprocessing (ensure normalized audio exists) ───
        job_service.transition_job(self.db_path, job_id, "preprocessing")
        sse.publish_stage(job_id, "preprocessing")
        job_service.update_progress(self.db_path, job_id, 0.05)
        logger.info("stage_started", stage="preprocessing", job_type="diarize")

        normalized_path = memo_dir / "normalized.wav"
        if not normalized_path.exists():
            # Try to normalize from source
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

        # Load existing transcript
        final_path = memo_dir / "transcript.final.json"
        if not final_path.exists():
            job_service.fail_job(self.db_path, job_id, "DIARIZE_FAILED", "No existing transcript to diarize")
            sse.publish_failed(job_id, "DIARIZE_FAILED", "No existing transcript to diarize")
            return

        try:
            existing_segments = json.loads(final_path.read_text())
        except Exception as exc:
            job_service.fail_job(self.db_path, job_id, "DIARIZE_FAILED", f"Failed to load transcript: {exc}")
            sse.publish_failed(job_id, "DIARIZE_FAILED", f"Failed to load transcript: {exc}")
            return

        job_service.update_progress(self.db_path, job_id, 0.1)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 2: Diarizing ───────────────────────────────────────
        t_diarize_start = time.monotonic()
        job_service.transition_job(self.db_path, job_id, "diarizing")
        sse.publish_stage(job_id, "diarizing")
        job_service.update_progress(self.db_path, job_id, 0.2)
        logger.info("stage_started", stage="diarizing", job_type="diarize")

        try:
            from app.services.diarization import run_diarization
            from app.services.diarization_merge import merge_diarization

            diarization_segments = await asyncio.to_thread(run_diarization, normalized_path)

            if diarization_segments:
                # Convert final.json format to the merge_diarization input format
                asr_segments = [
                    {
                        "start_ms": seg["start_ms"],
                        "end_ms": seg["end_ms"],
                        "text": seg["text"],
                        "confidence": seg.get("confidence", 1.0),
                    }
                    for seg in existing_segments
                ]
                merged = merge_diarization(asr_segments, diarization_segments)
                # Copy speaker_key back into existing segments
                for i, seg in enumerate(existing_segments):
                    if i < len(merged):
                        seg["speaker_key"] = merged[i].get("speaker_key")
                logger.info(
                    "diarization_completed",
                    speaker_segments=len(diarization_segments),
                    elapsed_s=round(time.monotonic() - t_diarize_start, 2),
                )
            else:
                logger.warning("diarization_no_segments", job_type="diarize")

        except Exception as exc:
            logger.warning("diarization_failed", error=str(exc))
            # Don't fail the job — just leave segments without speaker labels

        # Advance progress regardless of diarization success/failure
        job_service.update_progress(self.db_path, job_id, 0.7)
        sse.publish_progress(job_id, 0.7, "diarizing")

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 3: Finalizing ─────────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "finalizing")
        sse.publish_stage(job_id, "finalizing")
        job_service.update_progress(self.db_path, job_id, 0.85)
        logger.info("stage_started", stage="finalizing", job_type="diarize")

        # Re-persist transcript with updated speaker labels
        try:
            # Load raw output for persistence (it won't have speaker info, that's ok)
            raw_path = memo_dir / "transcript.raw.json"
            raw_output = json.loads(raw_path.read_text()) if raw_path.exists() else []

            # Build segments in persist_transcript format
            segments = [
                {
                    "start_ms": seg["start_ms"],
                    "end_ms": seg["end_ms"],
                    "text": seg["text"],
                    "confidence": seg.get("confidence", 1.0),
                    "speaker_key": seg.get("speaker_key"),
                }
                for seg in existing_segments
            ]

            await asyncio.to_thread(
                persist_transcript,
                memo_id,
                raw_output,
                segments,
                self.db_path,
            )
            logger.info("transcript_persisted")
        except Exception as exc:
            logger.error("transcript_persist_failed", error=str(exc))
            job_service.fail_job(self.db_path, job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            sse.publish_failed(job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            return

        # Create speaker rows
        try:
            from app.services.diarization import create_speaker_rows

            await asyncio.to_thread(create_speaker_rows, self.db_path, memo_id, segments)
        except Exception as exc:
            logger.warning("speaker_rows_failed", error=str(exc))

        job_service.update_progress(self.db_path, job_id, 0.95)

        if self.is_cancelled(job_id):
            self._do_cancel(job_id)
            return

        # ── Stage 4: Completed ──────────────────────────────────────
        job_service.transition_job(self.db_path, job_id, "completed")
        sse.publish_completed(job_id)
        logger.info("job_completed", job_type="diarize")

    def _do_cancel(self, job_id: str) -> None:
        """Execute cancellation for a job."""
        job_service.cancel_job(self.db_path, job_id)
        get_sse_manager().publish_cancelled(job_id)
        logger.info("job_cancelled")

    def _db_connection(self):
        """Return a db_connection context manager for this worker's database."""
        from app.db import db_connection

        return db_connection(self.db_path)

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
