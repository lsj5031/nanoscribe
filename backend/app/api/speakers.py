"""Speaker API endpoints – get, update, regenerate diarization."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.speakers import (
    PatchSpeakersRequest,
    PatchSpeakersResponse,
    SpeakerItem,
    SpeakersResponse,
)
from app.services import speakers as speakers_service

router = APIRouter(tags=["speakers"])

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Re-export for test monkeypatching
DATA_DIR = DATA_DIR


@router.get("/memos/{memo_id}/speakers", response_model=SpeakersResponse)
async def get_speakers(memo_id: str) -> SpeakersResponse:
    """Return memo-local speakers."""
    db_path = DATA_DIR / "nanoscribe.db"
    result = speakers_service.get_speakers(db_path, memo_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    return SpeakersResponse(
        memo_id=result["memo_id"],
        speakers=[SpeakerItem(**s) for s in result["speakers"]],
    )


@router.patch("/memos/{memo_id}/speakers", response_model=PatchSpeakersResponse)
async def patch_speakers(memo_id: str, body: PatchSpeakersRequest) -> PatchSpeakersResponse:
    """Update speaker display names and colors."""
    db_path = DATA_DIR / "nanoscribe.db"

    result = speakers_service.update_speakers(
        db_path,
        memo_id,
        [{"speaker_key": u.speaker_key, "display_name": u.display_name, "color": u.color} for u in body.updates],
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    return PatchSpeakersResponse(
        memo_id=result["memo_id"],
        speakers=[SpeakerItem(**s) for s in result["speakers"]],
    )


@router.post("/memos/{memo_id}/regenerate-diarization", status_code=201)
async def regenerate_diarization(memo_id: str) -> dict:
    """Create a diarization-only job to re-run speaker diarization."""
    db_path = DATA_DIR / "nanoscribe.db"

    try:
        job = speakers_service.create_diarization_job(db_path, memo_id)
    except ValueError:
        raise HTTPException(status_code=409, detail="Memo has an active job")

    if job is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    return job
