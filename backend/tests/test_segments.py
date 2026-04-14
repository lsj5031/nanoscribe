"""Tests for segment and audio API endpoints."""

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

    import app.api.segments as segments_mod
    import app.main as main_mod

    _orig_main = main_mod.DATA_DIR
    _orig_segments = segments_mod.DATA_DIR

    main_mod.DATA_DIR = data
    segments_mod.DATA_DIR = data

    yield data

    main_mod.DATA_DIR = _orig_main
    segments_mod.DATA_DIR = _orig_segments


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
    transcript_revision: int = 0,
) -> str:
    """Insert a memo directly into the DB and return its ID."""
    if memo_id is None:
        memo_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memos (id, title, source_kind, source_filename, status, "
        "transcript_revision, created_at, updated_at) "
        "VALUES (?, ?, 'upload', 'test.wav', ?, ?, ?, ?)",
        (memo_id, title, status, transcript_revision, now, now),
    )
    conn.commit()
    conn.close()
    return memo_id


def _insert_segment(
    db_path: Path,
    memo_id: str,
    ordinal: int = 1,
    start_ms: int = 0,
    end_ms: int = 5000,
    text: str = "Hello world",
    speaker_key: str | None = "spk0",
    confidence: float | None = 0.95,
) -> str:
    """Insert a segment directly into the DB and return its ID."""
    seg_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text, "
        "speaker_key, confidence, edited, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (seg_id, memo_id, ordinal, start_ms, end_ms, text, speaker_key, confidence, now, now),
    )
    conn.commit()
    conn.close()
    return seg_id


# ---------------------------------------------------------------------------
# GET /api/memos/{memoId}/segments
# ---------------------------------------------------------------------------


class TestGetSegments:
    """Tests for GET /api/memos/{memoId}/segments."""

    def test_returns_ordered_segments_with_revision(self, client: TestClient, tmp_path: Path) -> None:
        """Returns segments ordered by ordinal with memo revision."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db, transcript_revision=3)
        _insert_segment(db, memo_id, ordinal=2, start_ms=5000, end_ms=10000, text="Second")
        _insert_segment(db, memo_id, ordinal=1, start_ms=0, end_ms=5000, text="First")

        resp = client.get(f"/api/memos/{memo_id}/segments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert body["revision"] == 3
        assert len(body["segments"]) == 2
        assert body["segments"][0]["text"] == "First"
        assert body["segments"][0]["ordinal"] == 1
        assert body["segments"][1]["text"] == "Second"
        assert body["segments"][1]["ordinal"] == 2

    def test_404_for_nonexistent_memo(self, client: TestClient) -> None:
        """Returns 404 when the memo does not exist."""
        resp = client.get("/api/memos/nonexistent/segments")
        assert resp.status_code == 404

    def test_empty_segments_for_memo_with_no_segments(self, client: TestClient, tmp_path: Path) -> None:
        """Returns empty segments list for a memo with no segments."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db, transcript_revision=1)

        resp = client.get(f"/api/memos/{memo_id}/segments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert body["revision"] == 1
        assert body["segments"] == []

    def test_segment_fields(self, client: TestClient, tmp_path: Path) -> None:
        """Segment items contain all expected fields."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db, transcript_revision=5)
        _insert_segment(
            db, memo_id, ordinal=1, start_ms=100, end_ms=900, text="Test text", speaker_key="spk1", confidence=0.88
        )

        resp = client.get(f"/api/memos/{memo_id}/segments")
        assert resp.status_code == 200
        seg = resp.json()["segments"][0]
        assert seg["start_ms"] == 100
        assert seg["end_ms"] == 900
        assert seg["text"] == "Test text"
        assert seg["speaker_key"] == "spk1"
        assert seg["confidence"] == 0.88
        assert seg["edited"] is False


# ---------------------------------------------------------------------------
# GET /api/memos/{memoId}/audio
# ---------------------------------------------------------------------------


class TestGetAudio:
    """Tests for GET /api/memos/{memoId}/audio."""

    def test_returns_normalized_audio(self, client: TestClient, tmp_path: Path) -> None:
        """Returns audio_normalized.wav when it exists."""
        data = tmp_path / "data"
        memo_id = "test-audio-memo"
        _insert_memo(data / "nanoscribe.db", memo_id=memo_id)

        memo_dir = data / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)
        audio_file = memo_dir / "audio_normalized.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        resp = client.get(f"/api/memos/{memo_id}/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert len(resp.content) > 0

    def test_fallback_to_audio_original(self, client: TestClient, tmp_path: Path) -> None:
        """Falls back to audio_original.* when normalized is absent."""
        data = tmp_path / "data"
        memo_id = "test-fallback-memo"
        _insert_memo(data / "nanoscribe.db", memo_id=memo_id)

        memo_dir = data / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)
        audio_file = memo_dir / "audio_original.mp3"
        audio_file.write_bytes(b"ID3" + b"\x00" * 100)

        resp = client.get(f"/api/memos/{memo_id}/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"

    def test_404_when_no_audio_file(self, client: TestClient, tmp_path: Path) -> None:
        """Returns 404 when no audio file exists."""
        data = tmp_path / "data"
        memo_id = "test-noaudio-memo"
        _insert_memo(data / "nanoscribe.db", memo_id=memo_id)

        memo_dir = data / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)

        resp = client.get(f"/api/memos/{memo_id}/audio")
        assert resp.status_code == 404

    def test_404_for_nonexistent_memo(self, client: TestClient) -> None:
        """Returns 404 when the memo does not exist."""
        resp = client.get("/api/memos/nonexistent/audio")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/memos/{memoId}/segments
# ---------------------------------------------------------------------------


class TestPatchSegments:
    """Tests for PATCH /api/memos/{memoId}/segments."""

    def test_updates_segment_text_and_increments_revision(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH updates segment text, sets edited=1, and bumps revision."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db, transcript_revision=3)
        seg_id = _insert_segment(db, memo_id, text="Original text")

        resp = client.patch(
            f"/api/memos/{memo_id}/segments",
            json={"base_revision": 3, "updates": [{"segment_id": seg_id, "text": "Updated text"}]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert body["revision"] == 4
        assert len(body["updated_segments"]) == 1
        seg = body["updated_segments"][0]
        assert seg["id"] == seg_id
        assert seg["text"] == "Updated text"
        assert seg["edited"] is True

        # Verify in DB
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT text, edited FROM segments WHERE id = ?", (seg_id,)).fetchone()
        conn.close()
        assert row[0] == "Updated text"
        assert row[1] == 1

    def test_returns_409_when_base_revision_is_stale(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH returns 409 when base_revision doesn't match."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db, transcript_revision=5)
        _insert_segment(db, memo_id, text="Hello")

        resp = client.patch(
            f"/api/memos/{memo_id}/segments",
            json={"base_revision": 3, "updates": [{"segment_id": "any", "text": "New"}]},
        )
        assert resp.status_code == 409
        body = resp.json()
        # HTTPException wraps detail inside {"detail": ...}
        detail = body["detail"]
        assert detail["current_revision"] == 5
        assert len(detail["current_segments"]) == 1

    def test_returns_404_for_nonexistent_memo(self, client: TestClient) -> None:
        """PATCH returns 404 for nonexistent memo."""
        resp = client.patch(
            "/api/memos/nonexistent/segments",
            json={"base_revision": 0, "updates": [{"segment_id": "x", "text": "y"}]},
        )
        assert resp.status_code == 404

    def test_validates_request_body_missing_fields(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH returns 422 for missing required fields."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)

        # Missing base_revision
        resp = client.patch(
            f"/api/memos/{memo_id}/segments",
            json={"updates": [{"segment_id": "x", "text": "y"}]},
        )
        assert resp.status_code == 422

        # Missing updates
        resp = client.patch(
            f"/api/memos/{memo_id}/segments",
            json={"base_revision": 0},
        )
        assert resp.status_code == 422

        # Empty body
        resp = client.patch(f"/api/memos/{memo_id}/segments", json={})
        assert resp.status_code == 422

    def test_multiple_segment_updates_in_single_patch(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH can update multiple segments in a single request."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db, transcript_revision=1)
        seg1 = _insert_segment(db, memo_id, ordinal=1, text="First")
        seg2 = _insert_segment(db, memo_id, ordinal=2, start_ms=5000, end_ms=10000, text="Second")

        resp = client.patch(
            f"/api/memos/{memo_id}/segments",
            json={
                "base_revision": 1,
                "updates": [
                    {"segment_id": seg1, "text": "Updated first"},
                    {"segment_id": seg2, "text": "Updated second"},
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["revision"] == 2
        assert len(body["updated_segments"]) == 2
        texts = {s["id"]: s["text"] for s in body["updated_segments"]}
        assert texts[seg1] == "Updated first"
        assert texts[seg2] == "Updated second"
