"""Pipeline — sequential stage execution for transcription jobs.

Defines a ``Stage`` protocol and a ``SequentialPipeline`` that runs
stages in order, passing a shared ``PipelineContext`` between them.
Each stage owns a named slice of progress and reports failures via
the context's error state.

Usage::

    ctx = PipelineContext(job_id, memo_id, db_path, data_dir)
    stages = [PreprocessingStage(), TranscriptionStage(), ...]
    pipeline = SequentialPipeline(stages)
    await pipeline.run(ctx)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import structlog

from app.services.sse import SSEEventManager

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Context — mutable state flowing through pipeline stages
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Holds all state that flows through the pipeline stages.

    Stages read, write, and sometimes clear these fields.  The context
    is reset per job.
    """

    job_id: str
    memo_id: str
    db_path: Path
    data_dir: Path
    job_type: str = "transcribe"
    hotwords: str | None = None
    enable_diarization: bool = False

    # Populated during pipeline execution
    memo_dir: Path = field(init=False)
    source_path: Path = field(init=False)
    normalized_path: Path | None = None
    duration_ms: int | None = None
    result: dict[str, Any] | None = None  # transcription result
    cancelled: bool = False

    def __post_init__(self) -> None:
        self.memo_dir = self.data_dir / "memos" / self.memo_id
        self.source_path = self.memo_dir / "source.original"


# ---------------------------------------------------------------------------
# Stage protocol
# ---------------------------------------------------------------------------


class Stage(Protocol):
    """A single step in the transcription pipeline.

    Each stage has a human-readable ``name`` and a ``progress_range``
    ``(start, end)`` that represents its span of the overall 0–1 progress
    bar.  The ``run`` method executes the stage logic and returns ``True``
    to continue to the next stage, or ``False`` to abort the pipeline.
    """

    name: str
    progress_range: tuple[float, float]

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Sequential pipeline
# ---------------------------------------------------------------------------


class SequentialPipeline:
    """Runs a list of Stage adapters in order, passing a shared context."""

    def __init__(self, stages: list[Stage]) -> None:
        self.stages = stages

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        """Execute every stage in order.

        Returns ``True`` if all stages completed, ``False`` if any stage
        failed or the pipeline was cancelled.
        """
        for stage in self.stages:
            if cancel_check():
                ctx.cancelled = True
                logger.info("pipeline_cancelled", stage=stage.name)
                return False

            ok = await stage.run(ctx, sse, cancel_check)
            if not ok:
                if cancel_check():
                    ctx.cancelled = True
                    logger.info("pipeline_cancelled", stage=stage.name)
                return False
        return True


# ===========================================================================
# Concrete stage adapters
# ===========================================================================


class PreprocessingStage:
    """Normalize audio, extract duration, extract waveform peaks."""

    name = "preprocessing"
    progress_range = (0.0, 0.10)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service
        from app.services.normalization import (
            NormalizationError,
            extract_duration_ms,
            extract_waveform_peaks,
            normalize_audio,
        )

        # Publish stage
        job_service.transition_job(ctx.db_path, ctx.job_id, "preprocessing")
        sse.publish_stage(ctx.job_id, "preprocessing")
        job_service.update_progress(ctx.db_path, ctx.job_id, 0.05)
        logger.info("stage_started", stage="preprocessing")

        if cancel_check():
            return False

        if not ctx.source_path.exists():
            logger.error("source_file_missing", path=str(ctx.source_path))
            job_service.fail_job(ctx.db_path, ctx.job_id, "NORMALIZATION_FAILED", "Source file not found")
            sse.publish_failed(ctx.job_id, "NORMALIZATION_FAILED", "Source file not found")
            return False

        try:
            ctx.normalized_path = normalize_audio(ctx.source_path, ctx.memo_dir)
            logger.info("audio_normalized", output=str(ctx.normalized_path))
        except NormalizationError as exc:
            logger.error("normalization_failed", error=str(exc))
            job_service.fail_job(ctx.db_path, ctx.job_id, "NORMALIZATION_FAILED", str(exc))
            sse.publish_failed(ctx.job_id, "NORMALIZATION_FAILED", str(exc))
            return False

        try:
            ctx.duration_ms = extract_duration_ms(ctx.normalized_path)
            from app.db import db_connection

            with db_connection(ctx.db_path) as conn:
                conn.execute("UPDATE memos SET duration_ms = ? WHERE id = ?", (ctx.duration_ms, ctx.memo_id))
                conn.commit()
            logger.info("duration_extracted", duration_ms=ctx.duration_ms)
        except NormalizationError:
            logger.debug("duration_extraction_skipped")

        try:
            extract_waveform_peaks(ctx.normalized_path, ctx.memo_dir)
            sse.publish_waveform_ready(ctx.job_id, ctx.memo_id)
            logger.info("waveform_extracted")
        except NormalizationError:
            logger.debug("waveform_extraction_skipped")

        job_service.update_progress(ctx.db_path, ctx.job_id, self.progress_range[1])
        return True


class TranscriptionStage:
    """Run ASR (local or remote) with per-chunk progress."""

    name = "transcribing"
    progress_range = (0.10, 0.65)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service
        from app.services.engine_config import get_models
        from app.services.protocols import TranscriptionError

        t_start = time.monotonic()

        job_service.transition_job(ctx.db_path, ctx.job_id, "transcribing")
        sse.publish_stage(ctx.job_id, "transcribing")
        logger.info("stage_started", stage="transcribing")

        if cancel_check():
            return False

        progress_start, progress_end = self.progress_range

        def _chunk_callback(chunks_done: int, total_chunks: int) -> None:
            if total_chunks <= 0:
                return
            frac = chunks_done / total_chunks
            p = progress_start + frac * (progress_end - progress_start)
            job_service.update_progress(ctx.db_path, ctx.job_id, p)
            sse.publish_progress_threadsafe(
                ctx.job_id,
                p,
                stage="transcribing",
                detail={"chunks_done": chunks_done, "total_chunks": total_chunks},
            )

        try:
            if ctx.normalized_path is None:
                logger.error("transcription_skipped_no_normalized_path")
                job_service.fail_job(ctx.db_path, ctx.job_id, "NORMALIZATION_FAILED", "Normalized audio not available")
                sse.publish_failed(ctx.job_id, "NORMALIZATION_FAILED", "Normalized audio not available")
                return False

            models = get_models()
            result = await asyncio.to_thread(
                models.transcribe,
                ctx.normalized_path,
                hotwords=ctx.hotwords,
                chunk_callback=_chunk_callback,
            )
            elapsed = time.monotonic() - t_start
            segment_count = len(result.get("segments", []))
            logger.info(
                "transcription_completed",
                segment_count=segment_count,
                elapsed_s=round(elapsed, 2),
            )
        except TranscriptionError as exc:
            logger.error("transcription_failed", error=str(exc))
            job_service.fail_job(ctx.db_path, ctx.job_id, "ASR_FAILED", str(exc))
            sse.publish_failed(ctx.job_id, "ASR_FAILED", str(exc))
            return False
        except Exception as exc:
            logger.error("transcription_failed", error=str(exc), exc_info=True)
            job_service.fail_job(ctx.db_path, ctx.job_id, "ASR_FAILED", str(exc))
            sse.publish_failed(ctx.job_id, "ASR_FAILED", str(exc))
            return False

        job_service.update_progress(ctx.db_path, ctx.job_id, progress_end)
        sse.publish_progress(ctx.job_id, progress_end, "transcribing")

        ctx.result = result
        return True


class DiarizationStage:
    """Run speaker diarization and merge labels into segments."""

    name = "diarizing"
    progress_range = (0.65, 0.85)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service

        progress_start, progress_end = self.progress_range

        if not ctx.enable_diarization:
            job_service.update_progress(ctx.db_path, ctx.job_id, progress_end)
            sse.publish_progress(ctx.job_id, progress_end)
            return True

        t_start = time.monotonic()
        job_service.transition_job(ctx.db_path, ctx.job_id, "diarizing")
        sse.publish_stage(ctx.job_id, "diarizing")
        job_service.update_progress(ctx.db_path, ctx.job_id, progress_start)
        logger.info("stage_started", stage="diarizing")

        if cancel_check():
            return False

        try:
            from app.services.diarization import run_diarization
            from app.services.diarization_merge import merge_diarization

            if ctx.normalized_path is None:
                logger.warning("diarization_skipped_no_normalized_path")
                job_service.update_progress(ctx.db_path, ctx.job_id, progress_end)
                sse.publish_progress(ctx.job_id, progress_end, "diarizing")
                return True

            diarization_segments = await asyncio.to_thread(run_diarization, ctx.normalized_path)

            if diarization_segments and ctx.result:
                ctx.result["segments"] = merge_diarization(ctx.result["segments"], diarization_segments)
                logger.info(
                    "diarization_completed",
                    speaker_segments=len(diarization_segments),
                    elapsed_s=round(time.monotonic() - t_start, 2),
                )
        except Exception as exc:
            logger.warning("diarization_failed", error=str(exc))

        job_service.update_progress(ctx.db_path, ctx.job_id, progress_end)
        sse.publish_progress(ctx.job_id, progress_end, "diarizing")
        return True


class PersistenceStage:
    """Persist transcript to disk and SQLite, create speaker rows."""

    name = "finalizing"
    progress_range = (0.85, 0.95)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service
        from app.services.persist import persist_transcript

        progress_start, progress_end = self.progress_range

        if ctx.result is None:
            logger.error("persist_skipped_no_result")
            job_service.fail_job(ctx.db_path, ctx.job_id, "UNKNOWN", "No transcription result to persist")
            sse.publish_failed(ctx.job_id, "UNKNOWN", "No transcription result to persist")
            return False

        job_service.transition_job(ctx.db_path, ctx.job_id, "finalizing")
        sse.publish_stage(ctx.job_id, "finalizing")
        job_service.update_progress(ctx.db_path, ctx.job_id, progress_start)
        logger.info("stage_started", stage="finalizing")

        if cancel_check():
            return False

        try:
            await asyncio.to_thread(
                persist_transcript,
                ctx.memo_id,
                ctx.result["raw_output"],
                ctx.result["segments"],
                ctx.db_path,
            )
            logger.info("transcript_persisted")
        except Exception as exc:
            logger.error("transcript_persist_failed", error=str(exc))
            job_service.fail_job(ctx.db_path, ctx.job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            sse.publish_failed(ctx.job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            return False

        if ctx.enable_diarization:
            try:
                from app.services.diarization import create_speaker_rows

                await asyncio.to_thread(create_speaker_rows, ctx.db_path, ctx.memo_id, ctx.result["segments"])
            except Exception as exc:
                logger.warning("speaker_rows_failed", error=str(exc))

        job_service.update_progress(ctx.db_path, ctx.job_id, progress_end)
        return True


class CompletionStage:
    """Mark job as completed."""

    name = "completed"
    progress_range = (0.95, 1.0)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service

        job_service.transition_job(ctx.db_path, ctx.job_id, "completed")
        sse.publish_completed(ctx.job_id)
        logger.info("job_completed")
        return True


# ===========================================================================
# Diarize-only pipeline (skips transcription, runs diarization on existing)
# ===========================================================================


class DiarizePreprocessingStage:
    """Ensure normalized audio exists, load existing transcript."""

    name = "preprocessing"
    progress_range = (0.0, 0.10)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service
        from app.services.normalization import NormalizationError, normalize_audio

        job_service.transition_job(ctx.db_path, ctx.job_id, "preprocessing")
        sse.publish_stage(ctx.job_id, "preprocessing")
        job_service.update_progress(ctx.db_path, ctx.job_id, 0.05)
        logger.info("stage_started", stage="preprocessing", job_type="diarize")

        if cancel_check():
            return False

        normalized_path = ctx.memo_dir / "normalized.wav"
        if not normalized_path.exists():
            if not ctx.source_path.exists():
                job_service.fail_job(ctx.db_path, ctx.job_id, "NORMALIZATION_FAILED", "Source file not found")
                sse.publish_failed(ctx.job_id, "NORMALIZATION_FAILED", "Source file not found")
                return False
            try:
                ctx.normalized_path = normalize_audio(ctx.source_path, ctx.memo_dir)
            except NormalizationError as exc:
                job_service.fail_job(ctx.db_path, ctx.job_id, "NORMALIZATION_FAILED", str(exc))
                sse.publish_failed(ctx.job_id, "NORMALIZATION_FAILED", str(exc))
                return False
        else:
            ctx.normalized_path = normalized_path

        final_path = ctx.memo_dir / "transcript.final.json"
        if not final_path.exists():
            job_service.fail_job(ctx.db_path, ctx.job_id, "DIARIZE_FAILED", "No existing transcript to diarize")
            sse.publish_failed(ctx.job_id, "DIARIZE_FAILED", "No existing transcript to diarize")
            return False

        try:
            ctx.result = {"segments": json.loads(final_path.read_text())}
        except Exception as exc:
            job_service.fail_job(ctx.db_path, ctx.job_id, "DIARIZE_FAILED", f"Failed to load transcript: {exc}")
            sse.publish_failed(ctx.job_id, "DIARIZE_FAILED", f"Failed to load transcript: {exc}")
            return False

        job_service.update_progress(ctx.db_path, ctx.job_id, 0.1)
        return True


class DiarizeOnlyStage:
    """Run diarization on already-transcribed memo and merge labels."""

    name = "diarizing"
    progress_range = (0.10, 0.70)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service
        from app.services.diarization import run_diarization
        from app.services.diarization_merge import merge_diarization

        t_start = time.monotonic()
        job_service.transition_job(ctx.db_path, ctx.job_id, "diarizing")
        sse.publish_stage(ctx.job_id, "diarizing")
        job_service.update_progress(ctx.db_path, ctx.job_id, 0.2)
        logger.info("stage_started", stage="diarizing", job_type="diarize")

        if cancel_check():
            return False

        existing_segments = ctx.result["segments"] if ctx.result else []

        try:
            if ctx.normalized_path is None:
                logger.warning("diarization_skipped_no_normalized_path", job_type="diarize")
                job_service.update_progress(ctx.db_path, ctx.job_id, 0.7)
                sse.publish_progress(ctx.job_id, 0.7, "diarizing")
                return True

            diarization_segments = await asyncio.to_thread(run_diarization, ctx.normalized_path)

            if diarization_segments:
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
                for i, seg in enumerate(existing_segments):
                    if i < len(merged):
                        seg["speaker_key"] = merged[i].get("speaker_key")
                logger.info(
                    "diarization_completed",
                    speaker_segments=len(diarization_segments),
                    elapsed_s=round(time.monotonic() - t_start, 2),
                )
            else:
                logger.warning("diarization_no_segments", job_type="diarize")
        except Exception as exc:
            logger.warning("diarization_failed", error=str(exc))

        job_service.update_progress(ctx.db_path, ctx.job_id, 0.7)
        sse.publish_progress(ctx.job_id, 0.7, "diarizing")
        return True


class DiarizePersistenceStage:
    """Re-persist transcript with updated speaker labels."""

    name = "finalizing"
    progress_range = (0.70, 0.95)

    async def run(
        self,
        ctx: PipelineContext,
        sse: SSEEventManager,
        cancel_check: Callable[[], bool],
    ) -> bool:
        from app.services import jobs as job_service
        from app.services.persist import persist_transcript

        job_service.transition_job(ctx.db_path, ctx.job_id, "finalizing")
        sse.publish_stage(ctx.job_id, "finalizing")
        job_service.update_progress(ctx.db_path, ctx.job_id, 0.85)
        logger.info("stage_started", stage="finalizing", job_type="diarize")

        if cancel_check():
            return False

        existing_segments = ctx.result["segments"] if ctx.result else []
        raw_path = ctx.memo_dir / "transcript.raw.json"
        raw_output = json.loads(raw_path.read_text()) if raw_path.exists() else []

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

        try:
            await asyncio.to_thread(
                persist_transcript,
                ctx.memo_id,
                raw_output,
                segments,
                ctx.db_path,
            )
            logger.info("transcript_persisted")
        except Exception as exc:
            logger.error("transcript_persist_failed", error=str(exc))
            job_service.fail_job(ctx.db_path, ctx.job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            sse.publish_failed(ctx.job_id, "UNKNOWN", f"Failed to persist transcript: {exc}")
            return False

        try:
            from app.services.diarization import create_speaker_rows

            await asyncio.to_thread(create_speaker_rows, ctx.db_path, ctx.memo_id, segments)
        except Exception as exc:
            logger.warning("speaker_rows_failed", error=str(exc))

        job_service.update_progress(ctx.db_path, ctx.job_id, 0.95)
        return True


# ===========================================================================
# Pipeline builders
# ===========================================================================


def build_transcribe_pipeline() -> SequentialPipeline:
    """Build the full transcription pipeline."""
    return SequentialPipeline(
        [
            PreprocessingStage(),
            TranscriptionStage(),
            DiarizationStage(),
            PersistenceStage(),
            CompletionStage(),
        ]
    )


def build_diarize_pipeline() -> SequentialPipeline:
    """Build the diarize-only pipeline."""
    return SequentialPipeline(
        [
            DiarizePreprocessingStage(),
            DiarizeOnlyStage(),
            DiarizePersistenceStage(),
            CompletionStage(),
        ]
    )
