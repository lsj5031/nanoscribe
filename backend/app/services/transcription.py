"""FunASR transcription service — ASR with VAD segmentation, punctuation, timestamps.

VAL-TRANS-009: FunASR model produces transcript segments with timestamps.
VAL-TRANS-010: Segments persisted to database and transcript JSON.
VAL-TRANS-013: VAD segments audio for efficient processing.

This service runs FunASR AutoModel with:
  - ASR: Fun-ASR-Nano-2512 (requires trust_remote_code=True, remote_code path)
  - VAD: fsmn-vad (loaded separately)
  - Punctuation: ct-punc (loaded separately)

Pipeline:
  1. Load VAD + ASR + Punc models (lazy, once)
  2. Run VAD on normalized WAV → speech segments [[start_ms, end_ms], ...]
  3. Run ASR on full audio (without built-in VAD to avoid batch decoding bug)
     → produces text with token-level timestamps and confidence scores
  4. Run Punc restoration on the raw text
  5. Build segments from token timestamps, grouped by sentence boundaries
  6. Persist raw ASR output as transcript.raw.json
  7. Persist editor-ready transcript as transcript.final.json
  8. Create segment rows in SQLite
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Model identifiers
ASR_MODEL = _settings.asr_model
VAD_MODEL = _settings.vad_model
PUNC_MODEL = _settings.punc_model

# Sentence-ending punctuation for segment splitting
_SENTENCE_END = frozenset("。！？.!?;")

# VAD-chunked ASR parameters
_MERGE_GAP_MS = 800  # merge VAD segments closer than this
_MAX_CHUNK_MS = 30_000  # never merge beyond 30 s (fits easily in 8 GiB VRAM)
_CHUNK_BUFFER_MS = 200  # pad each chunk by this much to avoid clipping
_MIN_CHUNK_MS = 400  # skip chunks shorter than this (ASR unreliable)


def _get_remote_code_path() -> str | None:
    """Locate the FunASR Nano model.py for remote_code parameter.

    Fun-ASR-Nano-2512 is not registered in FunASR's model tables by default.
    It requires trust_remote_code=True and an explicit path to the model implementation.
    """
    try:
        import funasr.models.fun_asr_nano

        model_py = Path(funasr.models.fun_asr_nano.__file__).parent / "model.py"
        if model_py.exists():
            path = str(model_py)
            logger.info("remote_code_path_found", path=path)
            return path
        logger.warning("remote_code_path_missing", searched=str(model_py))
        return None
    except (ImportError, AttributeError):
        logger.warning("remote_code_path_not_locatable")
        return None


class TranscriptionError(Exception):
    """Raised when transcription fails."""

    pass


class TranscriptionModels:
    """FunASR model manager with ephemeral GPU inference.

    Models are *not* kept in GPU memory between inference steps — they are
    too large to coexist on an 8 GiB RTX 3070 (VAD+ASR+Punc ≈ 7.5 GiB).
    Instead, each ``run_*`` method creates a fresh AutoModel on the GPU,
    runs inference, then deletes it and clears VRAM before the next step.

    This adds ~2-5 s overhead per step (loading from disk cache) but
    guarantees that only one model occupies VRAM at a time, leaving room
    for inference tensors.

    Thread-safety: ``_infer_lock`` serialises GPU inference so that two
    concurrent transcription jobs don't compete for VRAM.
    """

    def __init__(self) -> None:
        self._device: str = "cpu"
        self._remote_code: str | None = None
        self._loaded: bool = False  # True once disk cache is verified
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()  # serialises GPU inference steps

    def _detect_device(self) -> str:
        """Detect best available device (cuda if available, else cpu)."""
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
        except ImportError:
            pass
        return "cpu"

    def load(self) -> None:
        """Verify that models are available and detect the inference device.

        Checks that each model directory exists in the ModelScope disk cache.
        If a model isn't cached yet, creating the AutoModel during inference
        will trigger the download automatically — so this method is a fast
        best-effort check, not a blocking download.

        Thread-safe: uses a lock to prevent concurrent double-loading
        when the startup preload and a first transcription job race.
        """
        with self._load_lock:
            if self._loaded:
                return

            try:
                from funasr import AutoModel  # noqa: F401
            except ImportError as e:
                raise TranscriptionError("FunASR is not installed") from e

            self._device = self._detect_device()
            self._remote_code = _get_remote_code_path()

            logger.info(
                "checking_model_cache",
                device=self._device,
            )

            # Quick disk-cache check for each model.  Missing models will
            # be downloaded on first inference — no need to block here.
            missing = []
            for label, model_id in [
                ("VAD", VAD_MODEL),
                ("ASR", ASR_MODEL),
                ("Punc", PUNC_MODEL),
            ]:
                cache_dir = self._model_cache_dir(model_id)
                if cache_dir and not cache_dir.is_dir():
                    missing.append(f"{label} ({model_id})")
                else:
                    logger.info("model_cached", model=label)

            if missing:
                logger.warning(
                    "models_not_cached",
                    missing=missing,
                )

            self._loaded = True
            logger.info("pipeline_ready", device=self._device)

    @property
    def is_loaded(self) -> bool:
        """Check if models are verified as cached on disk."""
        return self._loaded

    @property
    def device(self) -> str:
        """Return the target inference device."""
        return self._device

    @staticmethod
    def _model_cache_dir(model_id: str) -> Path | None:
        """Return the ModelScope cache directory for *model_id*, or None."""
        import os

        cache_root = os.environ.get("MODELSCOPE_CACHE")
        if not cache_root:
            cache_root = str(Path.home() / ".cache" / "modelscope")
        # Model IDs like "iic/speech_fsmn_vad" or "FunAudioLLM/Fun-ASR-Nano-2512"
        # are stored under <cache>/models/<org>/<model_name>/
        if "/" in model_id:
            org, name = model_id.split("/", 1)
        else:
            # Short aliases like "fsmn-vad" — can't resolve cache path
            return None
        return Path(cache_root) / "models" / org / name

    def _clear_vram(self) -> None:
        """Release cached CUDA memory back to the allocator."""
        if self._device.startswith("cuda"):
            try:
                import torch

                torch.cuda.empty_cache()
            except ImportError:
                pass

    # -- Ephemeral model factories -------------------------------------------------

    def _create_vad_model(self) -> Any:
        """Create an ephemeral VAD model on the inference device."""
        from funasr import AutoModel

        return AutoModel(
            model=VAD_MODEL,
            disable_update=True,
            model_hub="modelscope",
            device=self._device,
        )

    def _create_asr_model(self) -> Any:
        """Create an ephemeral ASR model on the inference device."""
        from funasr import AutoModel

        kwargs: dict[str, Any] = {
            "model": ASR_MODEL,
            "disable_update": True,
            "model_hub": "modelscope",
            "trust_remote_code": True,
            "device": self._device,
        }
        if self._remote_code:
            kwargs["remote_code"] = self._remote_code
        return AutoModel(**kwargs)

    def _create_punc_model(self) -> Any:
        """Create an ephemeral Punc model on the inference device."""
        from funasr import AutoModel

        return AutoModel(
            model=PUNC_MODEL,
            disable_update=True,
            model_hub="modelscope",
            device=self._device,
        )

    # -- Inference methods ---------------------------------------------------------

    def run_vad(self, audio_path: str | Path) -> list[list[int]]:
        """Run VAD on an audio file and return speech segments.

        Creates a VAD model on GPU, runs inference, then deletes it.

        Returns:
            List of [start_ms, end_ms] pairs for each speech segment.
        """
        if not self._loaded:
            raise TranscriptionError("Models not loaded — call load() first")

        logger.info("vad_start", audio=str(audio_path), device=self._device)
        t0 = time.monotonic()

        with self._infer_lock:
            model = self._create_vad_model()
            try:
                result = model.generate(input=str(audio_path))
                if not result or not result[0].get("value"):
                    logger.info("vad_done", segments=0, elapsed_s=round(time.monotonic() - t0, 2))
                    return []
                segments = result[0]["value"]
                logger.info(
                    "vad_done",
                    segments=len(segments),
                    total_speech_ms=sum(e - s for s, e in segments),
                    elapsed_s=round(time.monotonic() - t0, 2),
                )
                return segments
            except Exception as exc:
                logger.error("vad_failed", error=str(exc))
                raise TranscriptionError(f"VAD processing failed: {exc}") from exc
            finally:
                del model
                self._clear_vram()

    def run_asr_chunked(
        self,
        audio_path: str | Path,
        vad_segments: list[list[int]],
        hotwords: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run ASR on VAD-chunked audio to avoid GPU OOM on long files.

        Instead of feeding the entire audio to ASR at once (which OOMs on
        long files for GPUs with limited VRAM), this method:
          1. Merges adjacent VAD segments that are close together
          2. Extracts each chunk as a temporary WAV file
          3. Creates the ASR model **once** and processes all chunks
          4. Adjusts timestamps to be relative to the full audio
          5. Combines all results, then deletes the ASR model

        The ASR model is kept in VRAM for the entire chunk-processing
        phase (VAD is already done and deleted, so VRAM is free) and
        only deleted after all chunks are processed.

        Returns:
            List of result dicts with globally-adjusted timestamps.
        """
        if not vad_segments:
            return []

        merged = _merge_vad_segments(vad_segments)
        logger.info(
            "chunked_asr_start",
            raw_segments=len(vad_segments),
            merged_segments=len(merged),
            device=self._device,
        )

        all_results: list[dict[str, Any]] = []
        t_chunk_total = time.monotonic()

        with self._infer_lock:
            t_model_load = time.monotonic()
            model = self._create_asr_model()
            logger.info("asr_model_loaded", load_s=round(time.monotonic() - t_model_load, 2))
            try:
                for i, (start_ms, end_ms) in enumerate(merged):
                    # Extract chunk as temporary WAV (with padding)
                    t_chunk_start = time.monotonic()
                    chunk_info = _extract_chunk(audio_path, start_ms, end_ms)
                    if chunk_info is None:
                        logger.warning(
                            "chunk_skipped_too_short",
                            chunk_index=i,
                            start_ms=start_ms,
                            end_ms=end_ms,
                        )
                        continue
                    chunk_path, padded_start = chunk_info
                    logger.debug(
                        "chunk_extracted",
                        chunk_index=i,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        padded_start_ms=padded_start,
                        chunk_path=str(chunk_path),
                    )

                    try:
                        generate_kwargs: dict[str, Any] = {
                            "input": str(chunk_path),
                            "disable_pbar": True,
                        }
                        if hotwords:
                            generate_kwargs["hotword"] = hotwords

                        chunk_result = model.generate(**generate_kwargs)
                    except Exception as exc:
                        logger.warning(
                            "chunk_asr_failed",
                            chunk_index=i,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            error=str(exc),
                        )
                        continue
                    finally:
                        # Clean up temp file
                        try:
                            chunk_path.unlink()
                        except OSError:
                            pass

                    if not chunk_result:
                        continue

                    # Adjust timestamps to be relative to the full audio.
                    # Use padded_start (not start_ms) because time 0 in
                    # the extracted chunk WAV corresponds to padded_start
                    # in the original audio.
                    result = chunk_result[0]
                    offset_s = padded_start / 1000.0
                    timestamps = result.get("timestamps", [])
                    for ts in timestamps:
                        ts["start_time"] = round(ts.get("start_time", 0) + offset_s, 3)
                        ts["end_time"] = round(ts.get("end_time", 0) + offset_s, 3)

                    all_results.append(result)

                    chunk_text = result.get("text", "")
                    n_tokens = len(timestamps)
                    logger.info(
                        "chunk_done",
                        chunk_index=i + 1,
                        total_chunks=len(merged),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        tokens=n_tokens,
                        text_preview=chunk_text[:60] if chunk_text else "",
                        elapsed_s=round(time.monotonic() - t_chunk_start, 2),
                    )
            finally:
                del model
                self._clear_vram()

        total_elapsed = time.monotonic() - t_chunk_total
        logger.info(
            "chunked_asr_done",
            chunks_processed=len(all_results),
            total_tokens=sum(len(r.get("timestamps", [])) for r in all_results),
            elapsed_s=round(total_elapsed, 2),
        )

        return all_results

    def run_punc(self, text: str) -> str:
        """Run punctuation restoration on text.

        Creates a Punc model on GPU, runs inference, then deletes it.

        Returns:
            Text with restored punctuation.
        """
        if not self._loaded:
            raise TranscriptionError("Models not loaded — call load() first")

        logger.info("punc_start", text_length=len(text))
        t0 = time.monotonic()

        with self._infer_lock:
            model = self._create_punc_model()
            try:
                result = model.generate(input=text)
                if result and result[0].get("text"):
                    punc_text = result[0]["text"]
                    logger.info("punc_done", elapsed_s=round(time.monotonic() - t0, 2))
                    return punc_text
                logger.info("punc_done", result="unchanged", elapsed_s=round(time.monotonic() - t0, 2))
                return text
            except Exception as exc:
                logger.warning("punc_failed", error=str(exc))
                return text
            finally:
                del model
                self._clear_vram()

    def transcribe(
        self,
        audio_path: str | Path,
        hotwords: str | None = None,
    ) -> dict[str, Any]:
        """Full transcription pipeline: VAD → chunked ASR → Punc.

        Returns a dict with:
          - raw_output: The raw FunASR ASR result list
          - text: Combined transcript text (with punctuation)
          - segments: List of segment dicts with start_ms, end_ms, text, confidence
        """
        self.load()

        logger.info("transcribe_start", audio=str(audio_path), hotwords=hotwords)
        t0 = time.monotonic()

        # Step 1: Run VAD to get speech segments
        vad_segments = self.run_vad(audio_path)

        if not vad_segments:
            logger.info("transcribe_done", result="no_speech", elapsed_s=round(time.monotonic() - t0, 2))
            return {"raw_output": [], "text": "", "segments": []}

        # Step 2: Run ASR on VAD-chunked audio (avoids GPU OOM on long files)
        chunk_results = self.run_asr_chunked(audio_path, vad_segments, hotwords=hotwords)

        if not chunk_results:
            logger.info("transcribe_done", result="no_asr_output", elapsed_s=round(time.monotonic() - t0, 2))
            return {"raw_output": [], "text": "", "segments": []}

        # Combine text and timestamps from all chunks
        all_timestamps: list[dict[str, Any]] = []
        all_raw_text: list[str] = []
        all_punct_text: list[str] = []

        for result in chunk_results:
            raw_text = result.get("text_tn", result.get("text", "")).strip()
            punct_text = result.get("text", "").strip()
            if raw_text:
                all_raw_text.append(raw_text)
            if punct_text:
                all_punct_text.append(punct_text)
            timestamps = result.get("timestamps", [])
            if timestamps:
                all_timestamps.extend(timestamps)

        # Step 3: Run punctuation restoration on combined raw text
        combined_raw = " ".join(all_raw_text)
        combined_punct = " ".join(all_punct_text)

        if combined_raw:
            combined_punct = self.run_punc(combined_raw)

        # Step 4: Build segments from globally-adjusted timestamps
        if all_timestamps:
            segments = _build_segments_from_timestamps(all_timestamps)
            logger.info("segments_built", method="timestamps", count=len(segments))
        elif vad_segments:
            segments = _build_segments_from_vad(vad_segments, combined_punct or combined_raw)
            logger.info("segments_built", method="vad_fallback", count=len(segments))
        else:
            segments = [
                {
                    "start_ms": 0,
                    "end_ms": 0,
                    "text": combined_punct or combined_raw,
                    "confidence": 1.0,
                }
            ]
            logger.info("segments_built", method="fallback", count=1)

        combined_text = " ".join(str(seg["text"]) for seg in segments if str(seg["text"]).strip())

        logger.info(
            "transcribe_done",
            segment_count=len(segments),
            text_length=len(combined_text),
            elapsed_s=round(time.monotonic() - t0, 2),
        )

        return {
            "raw_output": chunk_results,
            "text": combined_text,
            "segments": segments,
        }


def _merge_vad_segments(
    vad_segments: list[list[int]],
    gap_threshold_ms: int = _MERGE_GAP_MS,
    max_duration_ms: int = _MAX_CHUNK_MS,
) -> list[list[int]]:
    """Merge adjacent VAD segments that are close together.

    Merges segments whose gap is ≤ *gap_threshold_ms* unless the
    resulting chunk would exceed *max_duration_ms*.  This reduces
    the number of ASR calls while keeping each chunk small enough
    to avoid GPU OOM.
    """
    if not vad_segments:
        return []

    merged: list[list[int]] = [list(vad_segments[0])]

    for start, end in vad_segments[1:]:
        prev = merged[-1]
        gap = start - prev[1]
        duration_if_merged = end - prev[0]

        if gap <= gap_threshold_ms and duration_if_merged <= max_duration_ms:
            prev[1] = end  # merge
        else:
            merged.append([start, end])

    return merged


def _extract_chunk(
    audio_path: str | Path,
    start_ms: int,
    end_ms: int,
) -> tuple[Path, int] | None:
    """Extract a chunk of audio as a temporary WAV file using ffmpeg.

    Pads the chunk by _CHUNK_BUFFER_MS on each side to avoid clipping
    words at segment boundaries.  Returns ``(chunk_path, padded_start_ms)``
    or None if the chunk is too short.

    The caller must use *padded_start_ms* (not *start_ms*) as the offset
    when adjusting timestamps, because time 0 in the extracted WAV
    corresponds to *padded_start_ms* in the full audio.
    """
    import subprocess
    import tempfile

    audio_path = Path(audio_path)

    # Apply buffer padding
    padded_start = max(0, start_ms - _CHUNK_BUFFER_MS)
    padded_end = end_ms + _CHUNK_BUFFER_MS
    chunk_duration_ms = padded_end - padded_start

    if chunk_duration_ms < _MIN_CHUNK_MS:
        return None

    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav",
        prefix=f"chunk_{padded_start}_",
        delete=False,
    )
    tmp.close()
    chunk_path = Path(tmp.name)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{padded_start}ms",
        "-i",
        str(audio_path),
        "-t",
        f"{chunk_duration_ms}ms",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(chunk_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        try:
            chunk_path.unlink()
        except OSError:
            pass
        return None

    if result.returncode != 0 or not chunk_path.exists() or chunk_path.stat().st_size == 0:
        try:
            chunk_path.unlink()
        except OSError:
            pass
        return None

    return chunk_path, padded_start


def _build_segments_from_timestamps(
    timestamps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build segments from token-level timestamps.

    Each timestamp has: token, start_time (seconds), end_time (seconds), score (confidence).

    Groups tokens into sentence-level segments by splitting on sentence-ending
    punctuation. Each segment gets the start time of its first token and end time
    of its last token. Confidence is the average of token scores.
    """
    if not timestamps:
        return []

    segments: list[dict[str, Any]] = []
    current_tokens: list[dict[str, Any]] = []

    for ts in timestamps:
        current_tokens.append(ts)

        token = ts.get("token", "")
        # Split on sentence-ending punctuation
        if token in _SENTENCE_END and len(current_tokens) > 1:
            seg = _tokens_to_segment(current_tokens)
            if seg:
                segments.append(seg)
            current_tokens = []

    # Remaining tokens
    if current_tokens:
        seg = _tokens_to_segment(current_tokens)
        if seg:
            segments.append(seg)

    return segments


def _tokens_to_segment(tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Convert a list of token dicts to a segment dict.

    Returns None if the resulting segment would be empty.
    """
    if not tokens:
        return None

    text = "".join(t.get("token", "") for t in tokens).strip()
    if not text:
        return None

    start_s = tokens[0].get("start_time", 0)
    end_s = tokens[-1].get("end_time", 0)

    # Average confidence from token scores
    scores = [t.get("score", 0) for t in tokens if t.get("score", 0) > 0]
    confidence = sum(scores) / len(scores) if scores else 1.0

    return {
        "start_ms": int(round(start_s * 1000)),
        "end_ms": int(round(end_s * 1000)),
        "text": text,
        "confidence": round(confidence, 4),
    }


def _build_segments_from_vad(
    vad_segments: list[list[int]],
    full_text: str,
) -> list[dict[str, Any]]:
    """Build segments from VAD timing when no token-level timestamps are available.

    Distributes the full text proportionally across VAD segments by character count.
    """
    if not vad_segments or not full_text:
        return []

    if len(vad_segments) == 1:
        return [
            {
                "start_ms": vad_segments[0][0],
                "end_ms": vad_segments[0][1],
                "text": full_text,
                "confidence": 1.0,
            }
        ]

    total_vad_ms = sum(end - start for start, end in vad_segments)
    if total_vad_ms <= 0:
        return [
            {
                "start_ms": vad_segments[0][0],
                "end_ms": vad_segments[-1][1],
                "text": full_text,
                "confidence": 1.0,
            }
        ]

    segments: list[dict[str, Any]] = []
    chars_per_ms = len(full_text) / total_vad_ms

    char_offset = 0
    for start_ms, end_ms in vad_segments:
        segment_ms = end_ms - start_ms
        n_chars = max(1, int(round(segment_ms * chars_per_ms)))
        n_chars = min(n_chars, len(full_text) - char_offset)

        if char_offset >= len(full_text):
            break

        seg_text = full_text[char_offset : char_offset + n_chars].strip()
        char_offset += n_chars

        if seg_text:
            segments.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": seg_text,
                    "confidence": 1.0,
                }
            )

    # Append remaining text to last segment
    if char_offset < len(full_text) and segments:
        remaining = full_text[char_offset:].strip()
        if remaining:
            segments[-1]["text"] += " " + remaining

    return segments


def persist_transcript(
    memo_id: str,
    raw_output: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    db_path: Path,
) -> None:
    """Persist raw and final transcripts to filesystem and segments to SQLite.

    Writes:
      - transcript.raw.json: Raw FunASR output
      - transcript.final.json: Editor-ready segment data
      - segments table rows in SQLite
    """
    from app.db import get_connection

    memo_dir = DATA_DIR / "memos" / memo_id

    # Persist raw output
    raw_path = memo_dir / "transcript.raw.json"
    raw_path.write_text(json.dumps(raw_output, default=str, ensure_ascii=False, indent=2))

    # Persist editor-ready transcript
    final_segments = []
    for i, seg in enumerate(segments):
        final_segments.append(
            {
                "ordinal": i + 1,
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "text": seg["text"],
                "confidence": seg["confidence"],
                "speaker_key": seg.get("speaker_key"),
            }
        )

    final_path = memo_dir / "transcript.final.json"
    final_path.write_text(json.dumps(final_segments, ensure_ascii=False, indent=2))

    # Insert segments into SQLite
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM segments WHERE memo_id = ?", (memo_id,))

        now = _now_iso()
        for i, seg in enumerate(segments):
            seg_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO segments
                    (id, memo_id, ordinal, start_ms, end_ms, text,
                     speaker_key, confidence, edited, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    seg_id,
                    memo_id,
                    i + 1,
                    seg["start_ms"],
                    seg["end_ms"],
                    seg["text"],
                    seg.get("speaker_key"),
                    seg["confidence"],
                    now,
                    now,
                ),
            )

        conn.execute(
            """
            UPDATE memos
            SET status = 'completed',
                transcript_revision = 1,
                speaker_count = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, memo_id),
        )

        conn.commit()
    finally:
        conn.close()

    logger.info("transcript_persisted", segment_count=len(segments), memo_id=memo_id)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Module-level singleton for model management
_models: TranscriptionModels | None = None


def get_models() -> TranscriptionModels:
    """Return the singleton TranscriptionModels instance."""
    global _models
    if _models is None:
        _models = TranscriptionModels()
    return _models


def is_model_ready() -> bool:
    """Check if the ASR model is loaded and ready."""
    if _models is None:
        return False
    return _models.is_loaded
