"""Library API endpoints – list, detail, delete memos."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import Response

from app.core.config import get_settings
from app.schemas.library import MemoCard, MemoDetail, PaginatedMemos
from app.services import library as library_service

router = APIRouter(tags=["library"])

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Re-export for test monkeypatching
DATA_DIR = DATA_DIR


@router.get("/memos", response_model=PaginatedMemos)
async def list_memos(
    q: str | None = Query(None, description="Search query for title and transcript text"),
    sort: str = Query("recent", description="Sort order: 'recent' or 'duration'"),
    status: str | None = Query(None, description="Filter by status (comma-separated)"),
    language: str | None = Query(None, description="Filter by language code"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginatedMemos:
    """List memos with pagination, search, sort, and filters.

    VAL-LIB-001: Returns paginated memo list with items, total, page, page_size.
    VAL-LIB-002: q param filters by title and transcript text.
    VAL-LIB-003: sort=recent orders by updated_at desc.
    VAL-LIB-004: sort=duration orders by duration_ms desc.
    VAL-LIB-005: status param filters by processing status.
    VAL-LIB-006: language param filters by detected or overridden language.
    VAL-LIB-017: Pagination respects page and page_size.
    VAL-LIB-019: Combined sort+filter+search produces correct intersection.
    """
    # Validate sort
    if sort not in library_service.VALID_SORTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sort '{sort}'. Must be one of: {', '.join(sorted(library_service.VALID_SORTS))}",
        )

    # Validate status
    if status and status.strip():
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        invalid = set(statuses) - library_service.VALID_STATUSES
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status value(s): {', '.join(sorted(invalid))}. "
                f"Valid values: {', '.join(sorted(library_service.VALID_STATUSES))}",
            )

    db_path = DATA_DIR / "nanoscribe.db"

    try:
        result = library_service.list_memos(
            db_path,
            q=q,
            sort=sort,
            status=status,
            language=language,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Enrich items with waveform URL
    items = []
    for item_data in result["items"]:
        # Check if waveform.json exists
        waveform_path = DATA_DIR / "memos" / item_data["id"] / "waveform.json"
        if waveform_path.exists():
            item_data["waveform_url"] = f"/api/memos/{item_data['id']}/waveform"
        items.append(MemoCard(**item_data))

    return PaginatedMemos(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/memos/{memo_id}", response_model=MemoDetail)
async def get_memo_detail(memo_id: str) -> MemoDetail:
    """Get full memo detail with job summary and export availability.

    VAL-LIB-016: Returns complete metadata with job summary and exports.
    """
    db_path = DATA_DIR / "nanoscribe.db"
    memo = library_service.get_memo_detail(db_path, memo_id)

    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")

    # Build latest_job if present
    latest_job = None
    if memo.get("latest_job"):
        from app.schemas.library import JobSummary

        latest_job = JobSummary(**memo["latest_job"])

    return MemoDetail(
        id=memo["id"],
        title=memo["title"],
        source_kind=memo["source_kind"],
        source_filename=memo["source_filename"],
        duration_ms=memo.get("duration_ms"),
        language_detected=memo.get("language_detected"),
        language_override=memo.get("language_override"),
        status=memo["status"],
        speaker_count=memo.get("speaker_count", 0),
        transcript_revision=memo.get("transcript_revision", 0),
        created_at=memo["created_at"],
        updated_at=memo["updated_at"],
        last_opened_at=memo.get("last_opened_at"),
        last_edited_at=memo.get("last_edited_at"),
        latest_job=latest_job,
        exports=memo.get("exports", {}),
    )


@router.delete("/memos/{memo_id}", status_code=204)
async def delete_memo(memo_id: str) -> Response:
    """Delete a memo and all associated data.

    VAL-LIB-014: Removes memo, segments, speakers, jobs, and filesystem artifacts.
    VAL-SEARCH-015: FTS5 index entries are removed.
    """
    db_path = DATA_DIR / "nanoscribe.db"
    deleted = library_service.delete_memo(db_path, DATA_DIR, memo_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Memo not found")

    return Response(status_code=204)
