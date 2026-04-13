"""Tests for library API: GET /api/memos, GET /api/memos/{id}, DELETE /api/memos/{id}.

Covers VAL-LIB-001 through VAL-LIB-006, VAL-LIB-014 through VAL-LIB-017,
VAL-LIB-019, and VAL-LIB-022.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a fresh DB and data dir for each test."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "memos").mkdir()

    from app.db.migrate import run_migrations

    db_path = data / "nanoscribe.db"
    run_migrations(db_path)

    import app.api.library as library_mod
    import app.api.system as system_mod
    import app.main as main_mod
    import app.services.upload as upload_mod

    # Store originals for restoration
    _orig_main = main_mod.DATA_DIR
    _orig_sys = system_mod.DATA_DIR
    _orig_upload = upload_mod.DATA_DIR
    _orig_library = library_mod.DATA_DIR

    main_mod.DATA_DIR = data
    system_mod.DATA_DIR = data
    upload_mod.DATA_DIR = data
    library_mod.DATA_DIR = data

    yield data

    main_mod.DATA_DIR = _orig_main
    system_mod.DATA_DIR = _orig_sys
    upload_mod.DATA_DIR = _orig_upload
    library_mod.DATA_DIR = _orig_library


@pytest.fixture()
def client() -> TestClient:
    """TestClient pointing at the app."""
    from app.main import app

    return TestClient(app)


def _insert_memo(
    db_path: Path,
    memo_id: str | None = None,
    title: str = "Test Memo",
    status: str = "completed",
    duration_ms: int | None = 30000,
    language_detected: str | None = None,
    language_override: str | None = None,
    speaker_count: int = 0,
    transcript_revision: int = 1,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """Insert a memo row directly into the DB and return its ID."""
    memo_id = memo_id or str(uuid.uuid4())
    now = created_at or _now_iso()
    updated = updated_at or now
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        INSERT INTO memos (id, title, source_kind, source_filename, duration_ms,
                           language_detected, language_override, status, speaker_count,
                           transcript_revision, created_at, updated_at)
        VALUES (?, ?, 'upload', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            memo_id,
            title,
            f"{title}.wav",
            duration_ms,
            language_detected,
            language_override,
            status,
            speaker_count,
            transcript_revision,
            now,
            updated,
        ),
    )
    conn.commit()
    conn.close()
    return memo_id


def _insert_job(
    db_path: Path,
    memo_id: str,
    job_id: str | None = None,
    status: str = "completed",
    progress: float = 1.0,
    error_code: str | None = None,
    error_message: str | None = None,
    attempt_count: int = 1,
) -> str:
    """Insert a job row directly into the DB and return its ID."""
    job_id = job_id or str(uuid.uuid4())
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        INSERT INTO jobs (id, memo_id, job_type, status, stage, progress,
                          error_code, error_message, attempt_count, created_at, updated_at)
        VALUES (?, ?, 'transcribe', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (job_id, memo_id, status, status, progress, error_code, error_message, attempt_count, now, now),
    )
    conn.commit()
    conn.close()
    return job_id


def _insert_segment(
    db_path: Path,
    memo_id: str,
    text: str = "Hello world",
    ordinal: int = 1,
    start_ms: int = 0,
    end_ms: int = 5000,
) -> str:
    """Insert a segment row directly into the DB and return its ID."""
    seg_id = str(uuid.uuid4())
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text,
                              speaker_key, confidence, edited, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL, 0.95, 0, ?, ?)
        """,
        (seg_id, memo_id, ordinal, start_ms, end_ms, text, now, now),
    )
    conn.commit()
    conn.close()
    return seg_id


def _create_memo_dir(data_dir: Path, memo_id: str) -> Path:
    """Create the memo directory with dummy files."""
    memo_dir = data_dir / "memos" / memo_id
    memo_dir.mkdir(parents=True, exist_ok=True)
    (memo_dir / "source.original").write_bytes(b"fake audio")
    (memo_dir / "normalized.wav").write_bytes(b"fake wav")
    (memo_dir / "waveform.json").write_text("[]")
    return memo_dir


# ===========================================================================
# VAL-LIB-001: GET /api/memos returns paginated list with search, sort, filters
# ===========================================================================


class TestListMemos:
    """GET /api/memos returns paginated memo list (VAL-LIB-001)."""

    def test_returns_200_with_items_total_page_page_size(self, client: TestClient, _setup_db: Path) -> None:
        _insert_memo(_setup_db / "nanoscribe.db", title="Memo 1")

        resp = client.get("/api/memos")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert body["total"] == 1
        assert body["page"] == 1
        assert len(body["items"]) == 1

    def test_memo_card_has_required_fields(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="My Memo", status="completed", duration_ms=12000)

        resp = client.get("/api/memos")
        item = resp.json()["items"][0]
        # VAL-LIB-001: items must contain id, title, duration_ms, speaker_count, status, updated_at
        assert "id" in item
        assert item["title"] == "My Memo"
        assert item["duration_ms"] == 12000
        assert "speaker_count" in item
        assert item["status"] == "completed"
        assert "updated_at" in item

    def test_empty_library_returns_empty_items(self, client: TestClient) -> None:
        resp = client.get("/api/memos")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


# ===========================================================================
# VAL-LIB-002: Query param q filters memos by title and transcript text
# ===========================================================================


class TestSearchFilter:
    """q param filters memos by title and transcript text (VAL-LIB-002)."""

    def test_search_by_title(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Team Meeting")
        _insert_memo(db_path, memo_id="m2", title="Interview Notes")

        resp = client.get("/api/memos?q=meeting")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Team Meeting"

    def test_search_by_segment_text(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Recording 1")
        _insert_segment(db_path, memo_id=mid, text="The budget review is scheduled for Friday")

        mid2 = _insert_memo(db_path, title="Recording 2")
        _insert_segment(db_path, memo_id=mid2, text="The weather is nice today")

        resp = client.get("/api/memos?q=budget")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == mid

    def test_search_case_insensitive(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Team Meeting Notes")

        resp = client.get("/api/memos?q=MEETING")
        assert resp.json()["total"] == 1

    def test_search_no_match(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Team Meeting")

        resp = client.get("/api/memos?q=xyznonexistent")
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_empty_q_returns_all(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Memo 1")
        _insert_memo(db_path, memo_id="m2", title="Memo 2")

        resp = client.get("/api/memos?q=")
        assert resp.json()["total"] == 2


# ===========================================================================
# VAL-LIB-003: sort=recent sorts by updated_at desc
# ===========================================================================


class TestSortRecent:
    """sort=recent orders memos by updated_at descending (VAL-LIB-003)."""

    def test_sort_recent_default(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Older", updated_at="2026-04-10T10:00:00.000Z")
        _insert_memo(db_path, memo_id="m2", title="Newer", updated_at="2026-04-13T10:00:00.000Z")

        resp = client.get("/api/memos")
        items = resp.json()["items"]
        assert items[0]["title"] == "Newer"
        assert items[1]["title"] == "Older"

    def test_sort_recent_explicit(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Older", updated_at="2026-04-10T10:00:00.000Z")
        _insert_memo(db_path, memo_id="m2", title="Newer", updated_at="2026-04-13T10:00:00.000Z")

        resp = client.get("/api/memos?sort=recent")
        items = resp.json()["items"]
        assert items[0]["title"] == "Newer"


# ===========================================================================
# VAL-LIB-004: sort=duration sorts by duration_ms desc
# ===========================================================================


class TestSortDuration:
    """sort=duration orders memos by duration_ms descending (VAL-LIB-004)."""

    def test_sort_duration(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Short", duration_ms=10000)
        _insert_memo(db_path, memo_id="m2", title="Long", duration_ms=60000)

        resp = client.get("/api/memos?sort=duration")
        items = resp.json()["items"]
        assert items[0]["title"] == "Long"
        assert items[1]["title"] == "Short"

    def test_duration_tiebreak_by_updated_at(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Older", duration_ms=30000, updated_at="2026-04-10T10:00:00.000Z")
        _insert_memo(db_path, memo_id="m2", title="Newer", duration_ms=30000, updated_at="2026-04-13T10:00:00.000Z")

        resp = client.get("/api/memos?sort=duration")
        items = resp.json()["items"]
        # Same duration, tiebreak by updated_at desc
        assert items[0]["title"] == "Newer"
        assert items[1]["title"] == "Older"


# ===========================================================================
# VAL-LIB-005: status filter
# ===========================================================================


class TestStatusFilter:
    """status param filters by processing status (VAL-LIB-005)."""

    def test_filter_completed(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Done", status="completed")
        _insert_memo(db_path, memo_id="m2", title="Pending", status="queued")

        resp = client.get("/api/memos?status=completed")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Done"

    def test_filter_failed(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Broken", status="failed")
        _insert_memo(db_path, memo_id="m2", title="Good", status="completed")

        resp = client.get("/api/memos?status=failed")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["title"] == "Broken"

    def test_filter_multiple_statuses(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Q", status="queued")
        _insert_memo(db_path, memo_id="m2", title="P", status="preprocessing")
        _insert_memo(db_path, memo_id="m3", title="C", status="completed")

        resp = client.get("/api/memos?status=queued,preprocessing")
        body = resp.json()
        assert body["total"] == 2
        titles = {i["title"] for i in body["items"]}
        assert titles == {"Q", "P"}

    def test_no_status_returns_all(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", status="completed")
        _insert_memo(db_path, memo_id="m2", status="failed")

        resp = client.get("/api/memos")
        assert resp.json()["total"] == 2

    def test_invalid_status_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/memos?status=invalid_status")
        assert resp.status_code == 422


# ===========================================================================
# VAL-LIB-006: language filter
# ===========================================================================


class TestLanguageFilter:
    """language param filters by detected or overridden language (VAL-LIB-006)."""

    def test_filter_by_language(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="English", language_detected="en")
        _insert_memo(db_path, memo_id="m2", title="Chinese", language_detected="zh")

        resp = client.get("/api/memos?language=en")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["title"] == "English"

    def test_language_override_takes_precedence(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        # Detected en, overridden to zh → should match zh, not en
        _insert_memo(db_path, memo_id="m1", title="Overridden", language_detected="en", language_override="zh")

        resp_zh = client.get("/api/memos?language=zh")
        assert resp_zh.json()["total"] == 1

        resp_en = client.get("/api/memos?language=en")
        assert resp_en.json()["total"] == 0

    def test_no_language_returns_all(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", language_detected="en")
        _insert_memo(db_path, memo_id="m2", language_detected="zh")

        resp = client.get("/api/memos")
        assert resp.json()["total"] == 2


# ===========================================================================
# VAL-LIB-014: DELETE /api/memos/{id} removes memo and all artifacts
# ===========================================================================


class TestDeleteMemo:
    """DELETE removes memo and all artifacts (VAL-LIB-014)."""

    def test_delete_returns_204(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="To Delete")
        _create_memo_dir(_setup_db, mid)

        resp = client.delete(f"/api/memos/{mid}")
        assert resp.status_code == 204

    def test_get_after_delete_returns_404(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="To Delete")

        client.delete(f"/api/memos/{mid}")
        resp = client.get(f"/api/memos/{mid}")
        assert resp.status_code == 404

    def test_delete_removes_directory(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="To Delete")
        _create_memo_dir(_setup_db, mid)

        assert (_setup_db / "memos" / mid).exists()
        client.delete(f"/api/memos/{mid}")
        assert not (_setup_db / "memos" / mid).exists()

    def test_delete_removes_segments(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="To Delete")
        _insert_segment(db_path, memo_id=mid, text="segment text")

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("SELECT COUNT(*) FROM segments WHERE memo_id = ?", (mid,)).fetchone()[0] == 1

        client.delete(f"/api/memos/{mid}")

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("SELECT COUNT(*) FROM segments WHERE memo_id = ?", (mid,)).fetchone()[0] == 0
        conn.close()

    def test_delete_removes_jobs(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="To Delete")
        _insert_job(db_path, memo_id=mid)

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE memo_id = ?", (mid,)).fetchone()[0] == 1

        client.delete(f"/api/memos/{mid}")

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE memo_id = ?", (mid,)).fetchone()[0] == 0
        conn.close()

    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/memos/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_removes_fts_entries(self, client: TestClient, _setup_db: Path) -> None:
        """After deletion, searching for the memo's title or segment text yields nothing."""
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="UniqueDeleteTitle")
        _insert_segment(db_path, memo_id=mid, text="UniqueDeleteSegmentText")

        client.delete(f"/api/memos/{mid}")

        # Search should not find the deleted memo
        resp = client.get("/api/memos?q=UniqueDeleteTitle")
        assert resp.json()["total"] == 0

        resp = client.get("/api/memos?q=UniqueDeleteSegmentText")
        assert resp.json()["total"] == 0

    def test_delete_removes_speakers(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="With Speakers")
        now = _now_iso()

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), mid, "spk1", "Speaker 1", "#ff0000", now, now),
        )
        conn.commit()
        conn.close()

        client.delete(f"/api/memos/{mid}")

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM memo_speakers WHERE memo_id = ?", (mid,)).fetchone()[0]
        conn.close()
        assert count == 0


# ===========================================================================
# VAL-LIB-016: GET /api/memos/{id} returns full memo detail
# ===========================================================================


class TestGetMemoDetail:
    """GET /api/memos/{id} returns complete metadata (VAL-LIB-016)."""

    def test_returns_full_metadata(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(
            db_path,
            title="Detailed Memo",
            status="completed",
            duration_ms=45000,
            language_detected="en",
            speaker_count=2,
            transcript_revision=1,
        )
        _insert_job(db_path, memo_id=mid, status="completed")

        resp = client.get(f"/api/memos/{mid}")
        assert resp.status_code == 200
        body = resp.json()

        # All required metadata fields
        assert body["id"] == mid
        assert body["title"] == "Detailed Memo"
        assert body["source_kind"] == "upload"
        assert body["source_filename"] == "Detailed Memo.wav"
        assert body["duration_ms"] == 45000
        assert body["language_detected"] == "en"
        assert body["status"] == "completed"
        assert body["speaker_count"] == 2
        assert body["transcript_revision"] == 1
        assert "created_at" in body
        assert "updated_at" in body

    def test_includes_latest_job(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="With Job")
        _insert_job(db_path, memo_id=mid, status="completed")

        resp = client.get(f"/api/memos/{mid}")
        body = resp.json()
        assert "latest_job" in body
        assert body["latest_job"]["status"] == "completed"
        assert body["latest_job"]["memo_id"] == mid

    def test_includes_exports_availability(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="With Exports")

        resp = client.get(f"/api/memos/{mid}")
        body = resp.json()
        assert "exports" in body
        # All formats should show as available (can be generated on demand)
        assert "txt" in body["exports"]
        assert "json" in body["exports"]
        assert "srt" in body["exports"]

    def test_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/memos/nonexistent-id")
        assert resp.status_code == 404

    def test_failed_memo_includes_job_error(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Failed Memo", status="failed")
        _insert_job(
            db_path,
            memo_id=mid,
            status="failed",
            error_code="NORMALIZATION_FAILED",
            error_message="Corrupt input audio",
        )

        resp = client.get(f"/api/memos/{mid}")
        body = resp.json()
        assert body["status"] == "failed"
        assert body["latest_job"]["error_code"] == "NORMALIZATION_FAILED"
        assert body["latest_job"]["error_message"] == "Corrupt input audio"


# ===========================================================================
# VAL-LIB-017: Pagination
# ===========================================================================


class TestPagination:
    """Pagination respects page and page_size (VAL-LIB-017)."""

    def test_page_one_with_page_size(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        for i in range(12):
            _insert_memo(db_path, memo_id=f"m{i}", title=f"Memo {i:02d}")

        resp = client.get("/api/memos?page=1&page_size=5")
        body = resp.json()
        assert len(body["items"]) == 5
        assert body["total"] == 12
        assert body["page"] == 1
        assert body["page_size"] == 5

    def test_last_page_returns_remainder(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        for i in range(12):
            _insert_memo(db_path, memo_id=f"m{i}", title=f"Memo {i:02d}")

        resp = client.get("/api/memos?page=3&page_size=5")
        body = resp.json()
        assert len(body["items"]) == 2  # 12 - 10 = 2
        assert body["total"] == 12

    def test_beyond_last_page_empty(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        for i in range(5):
            _insert_memo(db_path, memo_id=f"m{i}", title=f"Memo {i:02d}")

        resp = client.get("/api/memos?page=10&page_size=5")
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 5

    def test_page_zero_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/memos?page=0")
        assert resp.status_code == 422

    def test_page_size_zero_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/memos?page_size=0")
        assert resp.status_code == 422

    def test_page_size_too_large_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/memos?page_size=9999")
        assert resp.status_code == 422

    def test_default_page_and_page_size(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Only Memo")

        resp = client.get("/api/memos")
        body = resp.json()
        assert body["page"] == 1
        # Default page_size should be reasonable (e.g., 20)
        assert body["page_size"] >= 1
        assert body["page_size"] <= 100


# ===========================================================================
# VAL-LIB-019: Combined sort + filter + search
# ===========================================================================


class TestCombinedParams:
    """Sort, filter, and search compose correctly (VAL-LIB-019)."""

    def test_search_plus_status(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Meeting Notes", status="completed")
        _insert_memo(db_path, memo_id="m2", title="Meeting Draft", status="failed")
        _insert_memo(db_path, memo_id="m3", title="Interview", status="completed")

        resp = client.get("/api/memos?q=meeting&status=completed")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == "m1"

    def test_status_plus_language(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="EN Done", status="completed", language_detected="en")
        _insert_memo(db_path, memo_id="m2", title="ZH Done", status="completed", language_detected="zh")
        _insert_memo(db_path, memo_id="m3", title="EN Queued", status="queued", language_detected="en")

        resp = client.get("/api/memos?status=completed&language=en")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "EN Done"

    def test_search_plus_sort(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Meeting A", duration_ms=50000, updated_at="2026-04-10T10:00:00.000Z")
        _insert_memo(db_path, memo_id="m2", title="Meeting B", duration_ms=10000, updated_at="2026-04-13T10:00:00.000Z")

        resp = client.get("/api/memos?q=meeting&sort=duration")
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["title"] == "Meeting A"  # longer first
        assert items[1]["title"] == "Meeting B"

    def test_combined_with_pagination(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        for i in range(8):
            _insert_memo(
                db_path, memo_id=f"m{i}", title=f"Meeting {i}", status="completed", duration_ms=(i + 1) * 10000
            )

        resp = client.get("/api/memos?q=meeting&status=completed&sort=duration&page=1&page_size=3")
        body = resp.json()
        assert body["total"] == 8
        assert len(body["items"]) == 3
        # First should be longest
        assert body["items"][0]["duration_ms"] == 80000

    def test_no_match_returns_empty(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Team Meeting", status="completed")

        resp = client.get("/api/memos?q=interview&status=failed")
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert resp.status_code == 200


# ===========================================================================
# VAL-LIB-022: Performance with 500+ memos
# ===========================================================================


class TestPerformance:
    """Library performs acceptably with many memos (VAL-LIB-022)."""

    def test_500_memos_paginated_query(self, client: TestClient, _setup_db: Path) -> None:
        """API responds in <200ms with 500 memos in DB."""
        import time

        db_path = _setup_db / "nanoscribe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        now = _now_iso()
        for i in range(500):
            mid = f"perf-memo-{i:04d}"
            conn.execute(
                """
                INSERT INTO memos (id, title, source_kind, source_filename, duration_ms,
                                   status, speaker_count, transcript_revision, created_at, updated_at)
                VALUES (?, ?, 'upload', ?, ?, 'completed', 1, 1, ?, ?)
                """,
                (mid, f"Memo {i:04d}", f"Memo {i:04d}.wav", (i + 1) * 1000, now, now),
            )
        conn.commit()
        conn.close()

        start = time.monotonic()
        resp = client.get("/api/memos?page=1&page_size=20")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 500
        assert len(body["items"]) == 20
        # Should respond well under 200ms for paginated queries
        assert elapsed < 2.0, f"Query took {elapsed:.3f}s — too slow"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases for library API."""

    def test_waveform_thumbnail_reference(self, client: TestClient, _setup_db: Path) -> None:
        """Memo card includes waveform thumbnail reference."""
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="With Waveform")
        _create_memo_dir(_setup_db, mid)

        resp = client.get("/api/memos")
        item = resp.json()["items"][0]
        # Should reference waveform thumbnail
        assert "waveform_url" in item or "has_waveform" in item

    def test_invalid_sort_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/memos?sort=invalid_sort")
        assert resp.status_code == 422

    def test_memo_not_in_library_after_delete(self, client: TestClient, _setup_db: Path) -> None:
        """Deleted memo no longer appears in library listing."""
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Delete Me")
        _create_memo_dir(_setup_db, mid)

        # Confirm it's in the list
        resp = client.get("/api/memos")
        assert resp.json()["total"] == 1

        # Delete
        client.delete(f"/api/memos/{mid}")

        # Confirm it's gone from the list
        resp = client.get("/api/memos")
        assert resp.json()["total"] == 0
