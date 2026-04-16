"""OpenAI-compatible API endpoint — POST /v1/audio/transcriptions.

Provides a drop-in replacement for the OpenAI Whisper API so that tools
which speak the OpenAI transcription protocol (e.g. WhisperLiveKit clients,
obsidian plugins, IDE extensions) can use NanoScribe as a backend.

Key differences from the internal /api/memos upload flow:
  - Synchronous: the request blocks until transcription finishes.
  - Stateless: no memo/job rows are created in the database.
  - Response formats: json, text, srt, verbose_json, vtt.
  - Optional Bearer-token auth when NANOSCRIBE_API_KEY is set.
"""

from __future__ import annotations

import asyncio
import secrets
import tempfile
from pathlib import Path

import structlog
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from starlette.responses import PlainTextResponse, Response

from app.core.config import get_settings
from app.schemas.openai_compat import (
    ModelListResponse,
    ModelObject,
    SegmentItem,
    SimpleJsonResponse,
    VerboseJsonResponse,
    WordItem,
)
from app.services.normalization import NormalizationError, extract_duration_ms, normalize_audio
from app.services.transcription import _SENTENCE_END, TranscriptionError, get_models
from app.services.upload import SUPPORTED_EXTENSIONS

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["openai-compat"])

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Extend upload service's supported extensions with OpenAI-specific formats
_OPENAI_EXTRA_EXTENSIONS = frozenset(["mp4", "mpeg", "mpga"])
_SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS | _OPENAI_EXTRA_EXTENSIONS

# Valid response formats per OpenAI spec
_RESPONSE_FORMATS = frozenset(["json", "text", "srt", "verbose_json", "vtt"])


def _validate_api_key(authorization: str | None) -> None:
    """Validate the Bearer token if NANOSCRIBE_API_KEY is configured.

    If no key is configured, all requests are allowed (open mode).
    If a key is configured, requests must include a matching Bearer token.
    """
    api_key = _settings.api_key
    if not api_key:
        return  # Open mode — no auth required

    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Provide 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _is_supported_extension(filename: str) -> bool:
    """Check if the file extension is a supported audio format."""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in _SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
    temperature: float | None = Form(None),
    timestamp_granularities: list[str] | None = Form(None, alias="timestamp_granularities[]"),
    authorization: str | None = Header(None),
) -> Response:
    """OpenAI-compatible audio transcription endpoint.

    Accepts multipart/form-data with an audio file and returns the transcript
    in the requested format.  Processes the audio synchronously (no job queue).

    Parameters (OpenAI spec):
        file:  The audio file object (mp3, mp4, wav, etc.).
        model: Model ID — accepted but ignored (NanoScribe uses FunASR).
        language: ISO-639-1 language hint — accepted but currently ignored.
        prompt: Optional hotwords / context hint mapped to ``hotwords``.
        response_format: One of json, text, srt, verbose_json, vtt.
        temperature: Accepted but ignored.
        timestamp_granularities: For verbose_json — "word" and/or "segment".
    """
    # ── Auth ───────────────────────────────────────────────────────
    _validate_api_key(authorization)

    # ── Validate response format ───────────────────────────────────
    if response_format not in _RESPONSE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid response_format '{response_format}'. "
            f"Must be one of: {', '.join(sorted(_RESPONSE_FORMATS))}",
        )

    # ── Validate file ──────────────────────────────────────────────
    filename = file.filename or "unknown"
    if not _is_supported_extension(filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # ── Process audio in a temp directory ──────────────────────────
    with tempfile.TemporaryDirectory(prefix="nanoscribe_oai_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Write uploaded file to disk
        source_path = tmp_path / f"source.{filename.rsplit('.', 1)[-1]}"
        source_path.write_bytes(content)

        # Normalize to canonical WAV
        try:
            normalized_path = normalize_audio(source_path, tmp_path)
        except NormalizationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Audio normalization failed: {exc}",
            ) from exc

        # Run full transcription pipeline (VAD → ASR → Punc)
        try:
            models = get_models()
            # Ensure models are loaded (lazy first-call init)
            models.load()

            # Map 'prompt' param to hotwords for FunASR
            hotwords = prompt if prompt else None

            result = await asyncio.to_thread(
                models.transcribe,
                normalized_path,
                hotwords=hotwords,
            )
        except TranscriptionError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Transcription failed: {exc}",
            ) from exc
        except Exception as exc:
            logger.error("openai_transcription_failed", error=str(exc), exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Transcription failed due to an internal error.",
            ) from exc

        # ── Extract results inside the with-block ──────────────────
        #   (normalized_path is deleted when the temp dir is cleaned up)
        text = result.get("text", "")
        segments = result.get("segments", [])
        raw_output = result.get("raw_output", [])

        # Compute audio duration from the normalized WAV (not just segments,
        # which may be empty for silent files)
        duration = 0.0
        try:
            duration_ms = extract_duration_ms(normalized_path)
            duration = duration_ms / 1000.0
        except NormalizationError:
            # Fall back to last segment end time
            if segments:
                duration = segments[-1].get("end_ms", 0) / 1000.0

    # ── Build response in requested format ──────────────────────────
    if response_format == "text":
        return PlainTextResponse(content=text)

    if response_format == "json":
        return SimpleJsonResponse(text=text).model_dump()

    if response_format == "srt":
        return PlainTextResponse(content=_segments_to_srt(segments), media_type="text/srt")

    if response_format == "vtt":
        return PlainTextResponse(content=_segments_to_vtt(segments), media_type="text/vtt")

    # verbose_json
    include_words = timestamp_granularities is not None and "word" in timestamp_granularities
    include_segments = timestamp_granularities is None or "segment" in timestamp_granularities

    words: list[WordItem] = []
    seg_items: list[SegmentItem] = []

    if include_segments:
        for i, seg in enumerate(segments):
            seg_items.append(
                SegmentItem(
                    id=i,
                    start=seg.get("start_ms", 0) / 1000.0,
                    end=seg.get("end_ms", 0) / 1000.0,
                    text=seg.get("text", ""),
                )
            )

    # Word-level timestamps: FunASR token timestamps can be mapped
    # to words when the raw_output is available.  For now, we skip
    # word-level unless we have token-level data from the ASR result.
    # (Future: extract word boundaries from raw_output timestamps)
    if include_words and raw_output:
        words = _extract_words_from_raw(raw_output)

    return VerboseJsonResponse(
        task="transcribe",
        language=language or "en",
        duration=duration,
        text=text,
        words=words,
        segments=seg_items,
    ).model_dump()


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as WebVTT timestamp: HH:MM:SS.mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _segments_to_srt(segments: list[dict]) -> str:
    """Convert segment dicts to SRT subtitle format."""
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start = seg.get("start_ms", 0) / 1000.0
        end = seg.get("end_ms", 0) / 1000.0
        text = seg.get("text", "")
        lines.append(str(i))
        lines.append(f"{_format_timestamp_srt(start)} --> {_format_timestamp_srt(end)}")
        lines.append(text)
        lines.append("")  # blank line between entries
    return "\n".join(lines)


def _segments_to_vtt(segments: list[dict]) -> str:
    """Convert segment dicts to WebVTT subtitle format."""
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        start = seg.get("start_ms", 0) / 1000.0
        end = seg.get("end_ms", 0) / 1000.0
        text = seg.get("text", "")
        lines.append(f"{_format_timestamp_vtt(start)} --> {_format_timestamp_vtt(end)}")
        lines.append(text)
        lines.append("")  # blank line between entries
    return "\n".join(lines)


def _extract_words_from_raw(raw_output: list[dict]) -> list[WordItem]:
    """Extract word-level timestamps from FunASR raw output.

    FunASR returns token-level timestamps.  We concatenate tokens that
    don't end with whitespace into words, assigning start/end from the
    first/last token in each word.
    """
    words: list[WordItem] = []

    for chunk in raw_output:
        timestamps = chunk.get("timestamps", [])
        if not timestamps:
            continue

        # Accumulate tokens into words
        current_word_tokens: list[dict] = []

        for ts in timestamps:
            token = ts.get("token", "")

            current_word_tokens.append(ts)

            # A token that ends with a space or is sentence-ending
            # punctuation marks the end of a word.
            is_word_boundary = token.endswith(" ") or token in _SENTENCE_END_CHARS

            if is_word_boundary:
                word_text = "".join(t.get("token", "") for t in current_word_tokens).strip()
                if word_text:
                    word_start = current_word_tokens[0].get("start_time", 0.0)
                    word_end = current_word_tokens[-1].get("end_time", 0.0)
                    words.append(WordItem(word=word_text, start=round(word_start, 3), end=round(word_end, 3)))
                current_word_tokens = []

        # Flush remaining tokens
        if current_word_tokens:
            word_text = "".join(t.get("token", "") for t in current_word_tokens).strip()
            if word_text:
                word_start = current_word_tokens[0].get("start_time", 0.0)
                word_end = current_word_tokens[-1].get("end_time", 0.0)
                words.append(WordItem(word=word_text, start=round(word_start, 3), end=round(word_end, 3)))

    return words


# Re-export the sentence-end set from transcription for use in word extraction
_SENTENCE_END_CHARS = _SENTENCE_END


# ---------------------------------------------------------------------------
# Model discovery — OpenAI-compatible /v1/models
# ---------------------------------------------------------------------------

# Stable model IDs that OpenAI clients can reference.  The actual model
# used is always NanoScribe's configured FunASR pipeline; these IDs exist
# so that tools which query /v1/models before calling /v1/audio/transcriptions
# can discover what's available.
_MODEL_ENTRIES: list[dict[str, str]] = [
    {
        "id": "whisper-1",
        "owned_by": "nanoscribe",
    },
    {
        "id": "Fun-ASR-Nano-2512",
        "owned_by": "funasr",
    },
]

# Approximate creation timestamp for the models (Unix epoch seconds).
# Fun-ASR-Nano-2512 was released in late 2024.
_MODEL_CREATED_AT: int = 1735689600  # 2025-01-01T00:00:00Z


@router.get("/v1/models")
async def list_models(
    authorization: str | None = Header(None),
) -> ModelListResponse:
    """List available models (OpenAI-compatible).

    Returns the set of model IDs that can be passed to
    ``POST /v1/audio/transcriptions``.  When the pipeline models are
    not fully cached yet, the list is still returned — but callers can
    check ``/api/system/capabilities`` for readiness state.
    """
    _validate_api_key(authorization)

    data = [
        ModelObject(
            id=entry["id"],
            created=_MODEL_CREATED_AT,
            owned_by=entry["owned_by"],
        )
        for entry in _MODEL_ENTRIES
    ]
    return ModelListResponse(data=data)


@router.get("/v1/models/{model_id}")
async def retrieve_model(
    model_id: str,
    authorization: str | None = Header(None),
) -> ModelObject:
    """Retrieve a specific model by ID (OpenAI-compatible).

    Returns details for a single model.  Returns 404 if the model_id
    is not one of the supported IDs.
    """
    _validate_api_key(authorization)

    for entry in _MODEL_ENTRIES:
        if entry["id"] == model_id:
            return ModelObject(
                id=entry["id"],
                created=_MODEL_CREATED_AT,
                owned_by=entry["owned_by"],
            )

    raise HTTPException(
        status_code=404,
        detail=f"Model '{model_id}' not found.",
    )
