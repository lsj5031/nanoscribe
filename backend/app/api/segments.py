"""Segment and audio API endpoints for the transcript editor."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from app.core.config import get_settings
from app.schemas.segments import (
    ConflictResponse,
    PatchSegmentsRequest,
    PatchSegmentsResponse,
    SegmentItem,
    SegmentsResponse,
)
from app.services import segments as segments_service

router = APIRouter(tags=["segments"])

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Re-export for test monkeypatching
DATA_DIR = DATA_DIR


@router.get("/memos/{memo_id}/segments", response_model=SegmentsResponse)
async def get_segments(memo_id: str) -> SegmentsResponse:
    """Return ordered transcript segments and revision for a memo."""
    db_path = DATA_DIR / "nanoscribe.db"
    result = segments_service.get_segments(db_path, memo_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    return SegmentsResponse(
        memo_id=result["memo_id"],
        revision=result["revision"],
        segments=[SegmentItem(**s) for s in result["segments"]],
    )


@router.patch("/memos/{memo_id}/segments", response_model=PatchSegmentsResponse)
async def patch_segments(memo_id: str, body: PatchSegmentsRequest) -> PatchSegmentsResponse:
    """Update segment texts with optimistic concurrency control."""
    db_path = DATA_DIR / "nanoscribe.db"

    try:
        result = segments_service.patch_segments(
            db_path,
            memo_id,
            body.base_revision,
            [{"segment_id": u.segment_id, "text": u.text} for u in body.updates],
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Memo not found")
    except segments_service.ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=ConflictResponse(
                detail="Conflict: transcript has been modified",
                current_revision=exc.current_revision,
                current_segments=[SegmentItem(**s) for s in exc.current_segments],
            ).model_dump(),
        )

    return PatchSegmentsResponse(
        memo_id=result["memo_id"],
        revision=result["revision"],
        updated_segments=[SegmentItem(**s) for s in result["updated_segments"]],
    )


@router.get("/memos/{memo_id}/audio")
async def get_audio(memo_id: str) -> Response:
    """Serve the memo's normalized audio file as a streaming response."""
    # Guard against path traversal in memo_id
    if "/" in memo_id or "\\" in memo_id or ".." in memo_id:
        raise HTTPException(status_code=400, detail="Invalid memo ID")
    memo_dir = DATA_DIR / "memos" / memo_id
    # Verify resolved path stays within DATA_DIR/memos
    try:
        memo_dir.resolve().relative_to((DATA_DIR / "memos").resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memo ID")
    if not memo_dir.is_dir():
        raise HTTPException(status_code=404, detail="Memo not found")

    # Prefer normalized wav, fall back to any audio_original.*
    normalized = memo_dir / "audio_normalized.wav"
    if normalized.is_file():
        return _stream_audio(normalized, "audio/wav")

    # Look for any audio_original.* file
    for candidate in sorted(memo_dir.glob("audio_original.*")):
        content_type = _content_type_for(candidate.name)
        if content_type:
            return _stream_audio(candidate, content_type)

    raise HTTPException(status_code=404, detail="Audio file not found")


def _stream_audio(path: Path, content_type: str) -> StreamingResponse:
    """Return a StreamingResponse for an audio file."""
    file_size = path.stat().st_size
    chunk_size = 64 * 1024  # 64 KB

    def _iter():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter(),
        status_code=200,
        media_type=content_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        },
    )


def _content_type_for(filename: str) -> str | None:
    """Return a content-type for known audio extensions."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "webm": "audio/webm",
        "ogg": "audio/ogg",
        "opus": "audio/opus",
    }.get(ext)
