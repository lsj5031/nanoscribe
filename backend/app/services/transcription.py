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
import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Model identifiers
ASR_MODEL = _settings.asr_model
VAD_MODEL = _settings.vad_model
PUNC_MODEL = _settings.punc_model

# Sentence-ending punctuation for segment splitting
_SENTENCE_END = frozenset("。！？.!?;")


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
            logger.info("FunASR Nano remote_code path: %s", path)
            return path
        logger.warning("FunASR Nano model.py not found at %s", model_py)
        return None
    except (ImportError, AttributeError):
        logger.warning("Could not locate FunASR Nano model.py")
        return None


class TranscriptionError(Exception):
    """Raised when transcription fails."""

    pass


class TranscriptionModels:
    """Lazy-loaded FunASR model container.

    Models are loaded on first use and cached for the process lifetime.
    Thread-safety: designed for single-worker sequential GPU processing.
    """

    def __init__(self) -> None:
        self._asr_model: Any = None
        self._vad_model: Any = None
        self._punc_model: Any = None
        self._device: str = "cpu"

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
        """Load all models (VAD, ASR, Punc) if not already loaded."""
        if self._asr_model is not None:
            return

        try:
            from funasr import AutoModel
        except ImportError as e:
            raise TranscriptionError("FunASR is not installed") from e

        self._device = self._detect_device()
        logger.info("Loading FunASR models on device=%s ...", self._device)

        remote_code = _get_remote_code_path()

        # Load VAD model (standalone)
        logger.info("Loading VAD model: %s", VAD_MODEL)
        self._vad_model = AutoModel(
            model=VAD_MODEL,
            disable_update=True,
            model_hub="modelscope",
            device=self._device,
        )

        # Load ASR model WITHOUT built-in VAD/Punc (we run those separately)
        # This avoids the inference_with_vad batch decoding bug in Fun-ASR-Nano
        asr_kwargs: dict[str, Any] = {
            "model": ASR_MODEL,
            "disable_update": True,
            "model_hub": "modelscope",
            "trust_remote_code": True,
            "device": self._device,
        }
        if remote_code:
            asr_kwargs["remote_code"] = remote_code

        logger.info("Loading ASR model: %s", ASR_MODEL)
        self._asr_model = AutoModel(**asr_kwargs)

        # Load Punc model (standalone)
        logger.info("Loading Punc model: %s", PUNC_MODEL)
        self._punc_model = AutoModel(
            model=PUNC_MODEL,
            disable_update=True,
            model_hub="modelscope",
            device=self._device,
        )

        logger.info("FunASR models loaded successfully")

    @property
    def is_loaded(self) -> bool:
        """Check if models are loaded."""
        return self._asr_model is not None

    @property
    def device(self) -> str:
        """Return the device being used."""
        return self._device

    def run_vad(self, audio_path: str | Path) -> list[list[int]]:
        """Run VAD on an audio file and return speech segments.

        Returns:
            List of [start_ms, end_ms] pairs for each speech segment.
        """
        if self._vad_model is None:
            raise TranscriptionError("Models not loaded")

        try:
            result = self._vad_model.generate(input=str(audio_path))
            if not result or not result[0].get("value"):
                return []
            return result[0]["value"]
        except Exception as exc:
            raise TranscriptionError(f"VAD processing failed: {exc}") from exc

    def run_asr(self, audio_path: str | Path, hotwords: str | None = None) -> list[dict[str, Any]]:
        """Run ASR (without VAD) on an audio file.

        Returns:
            List of result dicts from FunASR with 'text', 'timestamps', etc.
        """
        if self._asr_model is None:
            raise TranscriptionError("Models not loaded")

        try:
            generate_kwargs: dict[str, Any] = {
                "input": str(audio_path),
                "disable_pbar": True,
            }
            if hotwords:
                generate_kwargs["hotword"] = hotwords

            result = self._asr_model.generate(**generate_kwargs)
            return result
        except NotImplementedError as exc:
            raise TranscriptionError(f"ASR processing failed (model limitation): {exc}") from exc
        except Exception as exc:
            raise TranscriptionError(f"ASR processing failed: {exc}") from exc

    def run_punc(self, text: str) -> str:
        """Run punctuation restoration on text.

        Returns:
            Text with restored punctuation.
        """
        if self._punc_model is None:
            raise TranscriptionError("Models not loaded")

        try:
            result = self._punc_model.generate(input=text)
            if result and result[0].get("text"):
                return result[0]["text"]
            return text
        except Exception as exc:
            logger.warning("Punc restoration failed, using raw text: %s", exc)
            return text

    def transcribe(
        self,
        audio_path: str | Path,
        hotwords: str | None = None,
    ) -> dict[str, Any]:
        """Full transcription pipeline: VAD → ASR → Punc.

        Returns a dict with:
          - raw_output: The raw FunASR ASR result list
          - text: Combined transcript text (with punctuation)
          - segments: List of segment dicts with start_ms, end_ms, text, confidence
        """
        self.load()

        # Step 1: Run VAD to get speech segments
        vad_segments = self.run_vad(audio_path)
        logger.info("VAD produced %d speech segments", len(vad_segments))

        if not vad_segments:
            return {"raw_output": [], "text": "", "segments": []}

        # Step 2: Run ASR on full audio (produces text with token-level timestamps)
        raw_output = self.run_asr(audio_path, hotwords=hotwords)

        if not raw_output:
            return {"raw_output": [], "text": "", "segments": []}

        result = raw_output[0]
        raw_text = result.get("text_tn", result.get("text", "")).strip()
        punct_text = result.get("text", "").strip()

        # Step 3: Get token-level timestamps for segment building
        timestamps = result.get("timestamps", [])

        # Step 4: Build segments from timestamps
        if timestamps:
            segments = _build_segments_from_timestamps(timestamps)
        elif vad_segments:
            # Fallback: use VAD timing if no token timestamps
            segments = _build_segments_from_vad(vad_segments, punct_text or raw_text)
        else:
            segments = [
                {
                    "start_ms": 0,
                    "end_ms": 0,
                    "text": punct_text or raw_text,
                    "confidence": 1.0,
                }
            ]

        combined_text = " ".join(str(seg["text"]) for seg in segments if str(seg["text"]).strip())

        return {
            "raw_output": raw_output,
            "text": combined_text,
            "segments": segments,
        }


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
                "speaker_key": None,
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
                     confidence, edited, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    seg_id,
                    memo_id,
                    i + 1,
                    seg["start_ms"],
                    seg["end_ms"],
                    seg["text"],
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

    logger.info("Persisted %d segments for memo %s", len(segments), memo_id)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


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
