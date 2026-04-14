"""Tests for speaker API endpoints."""

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

    import app.api.speakers as speakers_mod
    import app.main as main_mod

    _orig_main = main_mod.DATA_DIR
    _orig_speakers = speakers_mod.DATA_DIR

    main_mod.DATA_DIR = data
    speakers_mod.DATA_DIR = data

    yield data

    main_mod.DATA_DIR = _orig_main
    speakers_mod.DATA_DIR = _orig_speakers


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


def _insert_speaker(
    db_path: Path,
    memo_id: str,
    speaker_key: str = "spk0",
    display_name: str = "Speaker 1",
    color: str = "#00d4ff",
) -> str:
    """Insert a speaker directly into the DB and return its ID."""
    speaker_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (speaker_id, memo_id, speaker_key, display_name, color, now, now),
    )
    conn.commit()
    conn.close()
    return speaker_id


def _insert_job(
    db_path: Path,
    memo_id: str,
    status: str = "completed",
    job_type: str = "transcribe",
) -> str:
    """Insert a job directly into the DB and return its ID."""
    job_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO jobs (id, memo_id, job_type, status, progress, attempt_count, created_at) "
        "VALUES (?, ?, ?, ?, 0.0, 1, ?)",
        (job_id, memo_id, job_type, status, now),
    )
    conn.commit()
    conn.close()
    return job_id


# ---------------------------------------------------------------------------
# GET /api/memos/{memoId}/speakers
# ---------------------------------------------------------------------------


class TestGetSpeakers:
    """Tests for GET /api/memos/{memoId}/speakers."""

    def test_returns_speakers_list(self, client: TestClient, tmp_path: Path) -> None:
        """Returns speakers for an existing memo."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0", display_name="Speaker 1", color="#00d4ff")
        _insert_speaker(db, memo_id, speaker_key="spk1", display_name="Speaker 2", color="#f472b6")

        resp = client.get(f"/api/memos/{memo_id}/speakers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert len(body["speakers"]) == 2
        assert body["speakers"][0]["speaker_key"] == "spk0"
        assert body["speakers"][0]["display_name"] == "Speaker 1"
        assert body["speakers"][0]["color"] == "#00d4ff"
        assert body["speakers"][1]["speaker_key"] == "spk1"

    def test_returns_empty_list_for_memo_with_no_speakers(self, client: TestClient, tmp_path: Path) -> None:
        """Returns empty speakers list for a memo with no speakers."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)

        resp = client.get(f"/api/memos/{memo_id}/speakers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert body["speakers"] == []

    def test_404_for_nonexistent_memo(self, client: TestClient) -> None:
        """Returns 404 when the memo does not exist."""
        resp = client.get("/api/memos/nonexistent/speakers")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/memos/{memoId}/speakers
# ---------------------------------------------------------------------------


class TestPatchSpeakers:
    """Tests for PATCH /api/memos/{memoId}/speakers."""

    def test_updates_display_name_and_color(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH updates display_name and color for a speaker."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")

        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={
                "updates": [
                    {"speaker_key": "spk0", "display_name": "Alice", "color": "#ff6600"},
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert len(body["speakers"]) == 1
        assert body["speakers"][0]["display_name"] == "Alice"
        assert body["speakers"][0]["color"] == "#ff6600"

    def test_validates_color_format(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH rejects invalid color format."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")

        # Missing #
        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "Alice", "color": "ff6600"}]},
        )
        assert resp.status_code == 422

        # Too short
        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "Alice", "color": "#ff"}]},
        )
        assert resp.status_code == 422

        # Invalid chars
        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "Alice", "color": "#gggggg"}]},
        )
        assert resp.status_code == 422

    def test_validates_display_name_length(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH rejects display_name longer than 50 chars."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")

        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "A" * 51, "color": "#ff6600"}]},
        )
        assert resp.status_code == 422

    def test_404_for_nonexistent_memo(self, client: TestClient) -> None:
        """PATCH returns 404 for nonexistent memo."""
        resp = client.patch(
            "/api/memos/nonexistent/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "Alice", "color": "#ff6600"}]},
        )
        assert resp.status_code == 404

    def test_accepts_valid_color_lowercase(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH accepts valid lowercase hex color."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")

        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "Bob", "color": "#ab12cd"}]},
        )
        assert resp.status_code == 200

    def test_accepts_valid_color_uppercase(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH accepts valid uppercase hex color."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")

        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "Bob", "color": "#AB12CD"}]},
        )
        assert resp.status_code == 200

    def test_accepts_display_name_at_max_length(self, client: TestClient, tmp_path: Path) -> None:
        """PATCH accepts display_name of exactly 50 chars."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")

        resp = client.patch(
            f"/api/memos/{memo_id}/speakers",
            json={"updates": [{"speaker_key": "spk0", "display_name": "A" * 50, "color": "#ff6600"}]},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/memos/{memoId}/regenerate-diarization
# ---------------------------------------------------------------------------


class TestRegenerateDiarization:
    """Tests for POST /api/memos/{memoId}/regenerate-diarization."""

    def test_creates_diarization_job(self, client: TestClient, tmp_path: Path) -> None:
        """Creates a diarize job and returns 201."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        # Insert a completed job so memo has history
        _insert_job(db, memo_id, status="completed")

        resp = client.post(f"/api/memos/{memo_id}/regenerate-diarization")
        assert resp.status_code == 201
        body = resp.json()
        assert body["memo_id"] == memo_id
        assert body["job_type"] == "diarize"
        assert body["status"] == "queued"
        assert body["enable_diarization"] in (True, 1)

    def test_returns_409_when_job_active(self, client: TestClient, tmp_path: Path) -> None:
        """Returns 409 when an active job exists for the memo."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_job(db, memo_id, status="queued")

        resp = client.post(f"/api/memos/{memo_id}/regenerate-diarization")
        assert resp.status_code == 409

    def test_returns_404_when_memo_not_found(self, client: TestClient) -> None:
        """Returns 404 when the memo does not exist."""
        resp = client.post("/api/memos/nonexistent/regenerate-diarization")
        assert resp.status_code == 404

    def test_deletes_existing_speakers(self, client: TestClient, tmp_path: Path) -> None:
        """Deletes existing speakers before creating diarization job."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_speaker(db, memo_id, speaker_key="spk0")
        _insert_job(db, memo_id, status="completed")

        resp = client.post(f"/api/memos/{memo_id}/regenerate-diarization")
        assert resp.status_code == 201

        # Verify old speakers are gone
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM memo_speakers WHERE memo_id = ?", (memo_id,)).fetchone()[0]
        conn.close()
        assert count == 0

    def test_returns_409_when_transcribing(self, client: TestClient, tmp_path: Path) -> None:
        """Returns 409 when job is in transcribing state."""
        data = tmp_path / "data"
        db = data / "nanoscribe.db"
        memo_id = _insert_memo(db)
        _insert_job(db, memo_id, status="transcribing")

        resp = client.post(f"/api/memos/{memo_id}/regenerate-diarization")
        assert resp.status_code == 409
