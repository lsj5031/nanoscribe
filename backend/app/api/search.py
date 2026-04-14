"""Search API endpoint – GET /api/search."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.schemas.search import SearchResponse
from app.services import search as search_service

router = APIRouter(tags=["search"])

_settings = get_settings()
DATA_DIR = _settings.data_dir

# Re-export for test monkeypatching
DATA_DIR = DATA_DIR

MAX_QUERY_LENGTH = 1000


@router.get("/search", response_model=SearchResponse)
async def search(q: str = Query("", description="Search query")) -> SearchResponse:
    """Search memos by title and segment text.

    Returns structured results with match_type indicating whether the match
    was in the memo title or a transcript segment.
    """
    if not q or not q.strip():
        return SearchResponse(results=[], total=0)

    # Truncate very long queries
    q = q[:MAX_QUERY_LENGTH]

    db_path = DATA_DIR / "nanoscribe.db"

    try:
        result = search_service.search(db_path, q)
    except Exception:
        # Catch any unexpected FTS5 errors and return empty results
        return SearchResponse(results=[], total=0)

    return SearchResponse(**result)
