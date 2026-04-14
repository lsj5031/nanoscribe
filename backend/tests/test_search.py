"""Tests for search API: GET /api/search.

Covers title matches, segment matches, special characters, long queries,
case insensitivity, empty results, and result limits.
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
    import app.api.search as search_mod
    import app.api.system as system_mod
    import app.main as main_mod
    import app.services.upload as upload_mod

    _orig_main = main_mod.DATA_DIR
    _orig_sys = system_mod.DATA_DIR
    _orig_upload = upload_mod.DATA_DIR
    _orig_library = library_mod.DATA_DIR
    _orig_search = search_mod.DATA_DIR

    main_mod.DATA_DIR = data
    system_mod.DATA_DIR = data
    upload_mod.DATA_DIR = data
    library_mod.DATA_DIR = data
    search_mod.DATA_DIR = data

    yield data

    main_mod.DATA_DIR = _orig_main
    system_mod.DATA_DIR = _orig_sys
    upload_mod.DATA_DIR = _orig_upload
    library_mod.DATA_DIR = _orig_library
    search_mod.DATA_DIR = _orig_search


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
) -> str:
    """Insert a memo row directly into the DB and return its ID."""
    memo_id = memo_id or str(uuid.uuid4())
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        INSERT INTO memos (id, title, source_kind, source_filename, duration_ms,
                           status, speaker_count, transcript_revision, created_at, updated_at)
        VALUES (?, ?, 'upload', ?, ?, 'completed', 0, 1, ?, ?)
        """,
        (memo_id, title, f"{title}.wav", duration_ms, now, now),
    )
    conn.commit()
    conn.close()
    return memo_id


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


# ===========================================================================
# Basic search
# ===========================================================================


class TestBasicSearch:
    """Basic search returns results from titles and segments."""

    def test_search_by_title(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, memo_id="m1", title="Team Meeting")
        _insert_memo(db_path, memo_id="m2", title="Interview Notes")

        resp = client.get("/api/search?q=Meeting")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        title_matches = [r for r in body["results"] if r["match_type"] == "title"]
        assert len(title_matches) == 1
        assert title_matches[0]["memo_id"] == "m1"
        assert title_matches[0]["memo_title"] == "Team Meeting"
        assert title_matches[0]["segment_id"] is None

    def test_search_by_segment_text(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Recording")
        _insert_segment(db_path, memo_id=mid, text="The budget review is scheduled for Friday")

        resp = client.get("/api/search?q=budget")
        assert resp.status_code == 200
        body = resp.json()
        seg_matches = [r for r in body["results"] if r["match_type"] == "segment"]
        assert len(seg_matches) >= 1
        m = seg_matches[0]
        assert m["memo_id"] == mid
        assert m["segment_text"] is not None
        assert "budget" in m["segment_text"].lower()
        assert m["start_ms"] == 0
        assert m["end_ms"] == 5000

    def test_search_returns_both_title_and_segment_matches(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Project Planning")
        _insert_segment(db_path, memo_id=mid, text="We need to discuss project planning")

        resp = client.get("/api/search?q=planning")
        body = resp.json()
        match_types = {r["match_type"] for r in body["results"]}
        assert "title" in match_types
        assert "segment" in match_types


# ===========================================================================
# Empty query
# ===========================================================================


class TestEmptyQuery:
    """Empty query returns empty results."""

    def test_empty_q(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=")
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["total"] == 0

    def test_whitespace_only_q(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=%20%20%20")
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["total"] == 0

    def test_no_q_param(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search")
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["total"] == 0


# ===========================================================================
# Special characters
# ===========================================================================


class TestSpecialCharacters:
    """Special characters don't cause 500 errors."""

    def test_quotes(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=%22hello%22")
        assert resp.status_code == 200

    def test_asterisk(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=test*")
        assert resp.status_code == 200

    def test_unicode(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=%C3%A9l%C3%A8ve")
        assert resp.status_code == 200

    def test_cjk(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=%E4%BD%A0%E5%A5%BD")
        assert resp.status_code == 200

    def test_accented_chars(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=caf%C3%A9")
        assert resp.status_code == 200

    def test_fts_operators(self, client: TestClient, _setup_db: Path) -> None:
        """AND, OR, NOT operators should be escaped safely."""
        resp = client.get("/api/search?q=hello+AND+world")
        assert resp.status_code == 200

    def test_parentheses(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=(test)")
        assert resp.status_code == 200

    def test_colon(self, client: TestClient, _setup_db: Path) -> None:
        resp = client.get("/api/search?q=column:value")
        assert resp.status_code == 200


# ===========================================================================
# Long query
# ===========================================================================


class TestLongQuery:
    """Very long query returns 200."""

    def test_10000_char_query(self, client: TestClient, _setup_db: Path) -> None:
        long_q = "a" * 10000
        resp = client.get(f"/api/search?q={long_q}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["total"] == 0


# ===========================================================================
# Case insensitive
# ===========================================================================


class TestCaseInsensitive:
    """FTS5 search is case insensitive."""

    def test_case_insensitive_title(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Team Meeting")

        resp = client.get("/api/search?q=MEETING")
        body = resp.json()
        title_matches = [r for r in body["results"] if r["match_type"] == "title"]
        assert len(title_matches) == 1

    def test_case_insensitive_segment(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Recording")
        _insert_segment(db_path, memo_id=mid, text="Hello World")

        resp = client.get("/api/search?q=HELLO")
        body = resp.json()
        seg_matches = [r for r in body["results"] if r["match_type"] == "segment"]
        assert len(seg_matches) >= 1

    def test_mixed_case(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Team Meeting")

        resp = client.get("/api/search?q=TeAm")
        body = resp.json()
        assert body["total"] >= 1


# ===========================================================================
# Zero results
# ===========================================================================


class TestZeroResults:
    """Nonsense query returns empty results."""

    def test_nonsense_query(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        _insert_memo(db_path, title="Team Meeting")

        resp = client.get("/api/search?q=xyznonexistent12345")
        body = resp.json()
        assert body["results"] == []
        assert body["total"] == 0


# ===========================================================================
# Title-only match
# ===========================================================================


class TestTitleOnlyMatch:
    """Title match works when segments don't contain the query."""

    def test_title_only(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="UniqueBoardXyz Meeting")
        _insert_segment(db_path, memo_id=mid, text="The weather is sunny today")

        resp = client.get("/api/search?q=UniqueBoardXyz")
        body = resp.json()
        title_matches = [r for r in body["results"] if r["match_type"] == "title"]
        seg_matches = [r for r in body["results"] if r["match_type"] == "segment"]
        assert len(title_matches) == 1
        assert len(seg_matches) == 0


# ===========================================================================
# Segment-only match
# ===========================================================================


class TestSegmentOnlyMatch:
    """Segment match works when title doesn't contain the query."""

    def test_segment_only(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Daily Notes")
        _insert_segment(db_path, memo_id=mid, text="Revenue increased by 15 percent")

        resp = client.get("/api/search?q=Revenue")
        body = resp.json()
        title_matches = [r for r in body["results"] if r["match_type"] == "title"]
        seg_matches = [r for r in body["results"] if r["match_type"] == "segment"]
        assert len(title_matches) == 0
        assert len(seg_matches) == 1


# ===========================================================================
# Result limit
# ===========================================================================


class TestResultLimit:
    """Results are limited to 50."""

    def test_limit_50(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        now = _now_iso()

        # Create 60 memos with the same word in the title
        for i in range(60):
            mid = f"limit-memo-{i:04d}"
            conn.execute(
                "INSERT INTO memos (id, title, source_kind, source_filename, duration_ms, "
                "status, speaker_count, transcript_revision, created_at, updated_at) "
                "VALUES (?, ?, 'upload', ?, ?, 'completed', 0, 1, ?, ?)",
                (mid, f"Testing {i}", f"Testing {i}.wav", 1000, now, now),
            )
        conn.commit()
        conn.close()

        resp = client.get("/api/search?q=Testing")
        body = resp.json()
        assert len(body["results"]) <= 50
        assert body["total"] >= 50


# ===========================================================================
# Segment text preview
# ===========================================================================


class TestSegmentPreview:
    """Segment text is truncated to 200 chars."""

    def test_long_segment_truncated(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Long Segment Memo")
        long_text = "UniqueWord " + "x" * 300
        _insert_segment(db_path, memo_id=mid, text=long_text)

        resp = client.get("/api/search?q=UniqueWord")
        body = resp.json()
        seg_matches = [r for r in body["results"] if r["match_type"] == "segment"]
        assert len(seg_matches) >= 1
        assert len(seg_matches[0]["segment_text"]) <= 200

    def test_short_segment_full_text(self, client: TestClient, _setup_db: Path) -> None:
        db_path = _setup_db / "nanoscribe.db"
        mid = _insert_memo(db_path, title="Short Segment Memo")
        _insert_segment(db_path, memo_id=mid, text="Short preview text here")

        resp = client.get("/api/search?q=preview")
        body = resp.json()
        seg_matches = [r for r in body["results"] if r["match_type"] == "segment"]
        assert len(seg_matches) >= 1
        assert seg_matches[0]["segment_text"] == "Short preview text here"
