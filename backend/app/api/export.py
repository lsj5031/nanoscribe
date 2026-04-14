"""Export API endpoints – TXT, JSON, and SRT export for memos."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.services import export as export_service

router = APIRouter(tags=["export"])

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Re-export for test monkeypatching
DATA_DIR = DATA_DIR

SUPPORTED_FORMATS = {"txt", "json", "srt"}


@router.get("/memos/{memo_id}/export")
async def export_memo(memo_id: str, format: str = "txt") -> PlainTextResponse:
    """Export a memo in the requested format."""
    if format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported export format: {format}. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    db_path = DATA_DIR / "nanoscribe.db"

    export_fn = {
        "txt": export_service.export_txt,
        "json": export_service.export_json,
        "srt": export_service.export_srt,
    }[format]

    try:
        result = export_fn(db_path, memo_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Memo has no segments")

    if result is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    content, filename = result

    content_type = {
        "txt": "text/plain; charset=utf-8",
        "json": "application/json; charset=utf-8",
        "srt": "text/srt; charset=utf-8",
    }[format]

    return PlainTextResponse(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
