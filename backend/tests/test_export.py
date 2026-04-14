"""Tests for export API endpoints."""

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

    import app.api.export as export_mod
    import app.main as main_mod

    _orig_main = main_mod.DATA_DIR
    _orig_export = export_mod.DATA_DIR

    main_mod.DATA_DIR = data
    export_mod.DATA_DIR = data

    yield data

    main_mod.DATA_DIR = _orig_main
    export_mod.DATA_DIR = _orig_export


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
    transcript_revision: int = 0,
) -> str:
    """Insert a memo directly into the DB and return its ID."""
    if memo_id is None:
        memo_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memos (id, title, source_kind, source_filename, status, "
        "duration_ms, transcript_revision, created_at, updated_at) "
        "VALUES (?, ?, 'upload', 'test.wav', ?, ?, ?, ?, ?)",
        (memo_id, title, status, duration_ms, transcript_revision, now, now),
    )
    conn.commit()
    conn.close()
    return memo_id


def _insert_segment(
    db_path: Path,
    memo_id: str,
    ordinal: int,
    start_ms: int,
    end_ms: int,
    text: str,
    speaker_key: str | None = None,
    edited: bool = False,
) -> str:
    """Insert a segment directly into the DB and return its ID."""
    seg_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text, "
        "speaker_key, edited, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (seg_id, memo_id, ordinal, start_ms, end_ms, text, speaker_key, int(edited), now, now),
    )
    conn.commit()
    conn.close()
    return seg_id


def _insert_speaker(
    db_path: Path,
    memo_id: str,
    speaker_key: str,
    display_name: str,
    color: str = "#ff0000",
) -> str:
    """Insert a speaker into the DB and return its ID."""
    spk_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (spk_id, memo_id, speaker_key, display_name, color, now, now),
    )
    conn.commit()
    conn.close()
    return spk_id


def _seed_memo_with_segments(
    db_path: Path,
    memo_id: str | None = None,
) -> str:
    """Create a memo with two segments and two speakers."""
    memo_id = _insert_memo(db_path, memo_id=memo_id, title="Test Memo", duration_ms=10500)
    _insert_speaker(db_path, memo_id, "spk0", "Speaker 1")
    _insert_speaker(db_path, memo_id, "spk1", "Speaker 2")
    _insert_segment(db_path, memo_id, 1, 0, 5000, "Hello world", speaker_key="spk0")
    _insert_segment(db_path, memo_id, 2, 5000, 10500, "And this is the second segment", speaker_key="spk1")
    return memo_id


# ---------------------------------------------------------------------------
# TXT export tests
# ---------------------------------------------------------------------------


class TestTxtExport:
    """Tests for TXT export format."""

    def test_txt_has_correct_format(self, client: TestClient, tmp_path: Path) -> None:
        """TXT export has correct format with timestamps and speakers."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=txt")
        assert resp.status_code == 200

        content = resp.text
        assert "Speaker 1 (00:00):" in content
        assert "Hello world" in content
        assert "Speaker 2 (00:05):" in content
        assert "And this is the second segment" in content

    def test_txt_content_disposition(self, client: TestClient, tmp_path: Path) -> None:
        """TXT export has Content-Disposition header for download."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=txt")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        assert "Test Memo.txt" in resp.headers["content-disposition"]

    def test_txt_content_type(self, client: TestClient, tmp_path: Path) -> None:
        """TXT export has text/plain content type."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=txt")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]

    def test_txt_without_speakers(self, client: TestClient, tmp_path: Path) -> None:
        """TXT export works without speaker labels."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _insert_memo(db_path)
        _insert_segment(db_path, memo_id, 1, 0, 5000, "No speaker text")

        resp = client.get(f"/api/memos/{memo_id}/export?format=txt")
        assert resp.status_code == 200
        assert "(00:00):" in resp.text
        assert "No speaker text" in resp.text


# ---------------------------------------------------------------------------
# JSON export tests
# ---------------------------------------------------------------------------


class TestJsonExport:
    """Tests for JSON export format."""

    def test_json_has_correct_structure(self, client: TestClient, tmp_path: Path) -> None:
        """JSON export has correct top-level structure."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=json")
        assert resp.status_code == 200

        data = resp.json()
        assert data["memo_id"] == memo_id
        assert data["title"] == "Test Memo"
        assert data["duration_ms"] == 10500
        assert "exported_at" in data
        assert isinstance(data["segments"], list)
        assert len(data["segments"]) == 2

    def test_json_segment_structure(self, client: TestClient, tmp_path: Path) -> None:
        """JSON segments have the expected fields."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=json")
        assert resp.status_code == 200

        seg = resp.json()["segments"][0]
        assert seg["ordinal"] == 1
        assert seg["start_ms"] == 0
        assert seg["end_ms"] == 5000
        assert seg["speaker_key"] == "spk0"
        assert seg["speaker_name"] == "Speaker 1"
        assert seg["text"] == "Hello world"

    def test_json_content_type(self, client: TestClient, tmp_path: Path) -> None:
        """JSON export has application/json content type."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    def test_json_exported_at_is_iso_format(self, client: TestClient, tmp_path: Path) -> None:
        """JSON exported_at is a valid ISO timestamp."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=json")
        data = resp.json()
        # Should be parseable as ISO format
        assert "T" in data["exported_at"]
        assert data["exported_at"].endswith("Z")


# ---------------------------------------------------------------------------
# SRT export tests
# ---------------------------------------------------------------------------


class TestSrtExport:
    """Tests for SRT export format."""

    def test_srt_has_correct_timestamp_format(self, client: TestClient, tmp_path: Path) -> None:
        """SRT export has HH:MM:SS,mmm timestamp format."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=srt")
        assert resp.status_code == 200

        content = resp.text
        assert "00:00:00,000 --> 00:00:05,000" in content
        assert "00:00:05,000 --> 00:00:10,500" in content

    def test_srt_has_numbering(self, client: TestClient, tmp_path: Path) -> None:
        """SRT entries are numbered sequentially."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=srt")
        assert resp.status_code == 200

        content = resp.text
        lines = content.strip().split("\n")
        # First entry: "1", timestamp line, text line
        assert lines[0] == "1"
        # Second entry starts after blank line
        # Find line "2"
        assert "2\n" in content or "\n2\n" in content

    def test_srt_has_speaker_labels(self, client: TestClient, tmp_path: Path) -> None:
        """SRT entries include speaker labels as prefix."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=srt")
        assert resp.status_code == 200

        content = resp.text
        assert "Speaker 1: Hello world" in content
        assert "Speaker 2: And this is the second segment" in content

    def test_srt_content_type(self, client: TestClient, tmp_path: Path) -> None:
        """SRT export has text/srt content type."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=srt")
        assert resp.status_code == 200
        assert "text/srt" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestExportErrors:
    """Tests for export error handling."""

    def test_404_nonexistent_memo(self, client: TestClient) -> None:
        """Returns 404 for nonexistent memo."""
        resp = client.get("/api/memos/nonexistent/export?format=txt")
        assert resp.status_code == 404
        assert "Memo not found" in resp.json()["detail"]

    def test_404_no_segments(self, client: TestClient, tmp_path: Path) -> None:
        """Returns 404 for memo with no segments."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _insert_memo(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=txt")
        assert resp.status_code == 404
        assert "no segments" in resp.json()["detail"].lower()

    def test_422_unsupported_format(self, client: TestClient, tmp_path: Path) -> None:
        """Returns 422 for unsupported format."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _seed_memo_with_segments(db_path)

        resp = client.get(f"/api/memos/{memo_id}/export?format=pdf")
        assert resp.status_code == 422
        assert "Unsupported" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Edited text tests
# ---------------------------------------------------------------------------


class TestExportEditedText:
    """Tests that export reflects edited text, not original."""

    def test_export_reflects_edited_text(self, client: TestClient, tmp_path: Path) -> None:
        """Export reflects the current edited text from the segments table."""
        db_path = tmp_path / "data" / "nanoscribe.db"
        memo_id = _insert_memo(db_path, title="Edited Memo")
        _insert_segment(db_path, memo_id, 1, 0, 5000, "Original text", speaker_key="spk0", edited=False)
        _insert_speaker(db_path, memo_id, "spk0", "Speaker 1")

        # Edit the segment directly in DB
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE segments SET text = 'Edited text', edited = 1 WHERE memo_id = ?", (memo_id,))
        conn.commit()
        conn.close()

        # TXT should reflect edited text
        resp = client.get(f"/api/memos/{memo_id}/export?format=txt")
        assert resp.status_code == 200
        assert "Edited text" in resp.text
        assert "Original text" not in resp.text

        # JSON should also reflect edited text
        resp = client.get(f"/api/memos/{memo_id}/export?format=json")
        assert resp.status_code == 200
        assert resp.json()["segments"][0]["text"] == "Edited text"

        # SRT should also reflect edited text
        resp = client.get(f"/api/memos/{memo_id}/export?format=srt")
        assert resp.status_code == 200
        assert "Edited text" in resp.text
        assert "Original text" not in resp.text
