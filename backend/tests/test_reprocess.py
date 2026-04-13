"""Tests for POST /api/memos/{id}/reprocess endpoint.

Covers:
  - Reprocess creates new transcription job
  - Does not silently overwrite user edits
  - Uses current memo settings
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("NANOSCRIBE_DATA_DIR", "/tmp/nanoscribe-test-reprocess")
os.environ.setdefault("NANOSCRIBE_STATIC_DIR", "/tmp/nanoscribe-test-static")

from app.db import get_connection
from app.db.migrate import run_migrations


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _insert_memo(
    db_path: Path,
    memo_id: str | None = None,
    status: str = "completed",
    transcript_revision: int = 1,
    title: str = "Test Memo",
    source_filename: str = "test.wav",
    hotwords: str | None = None,
    language_override: str | None = None,
) -> str:
    memo_id = memo_id or str(uuid.uuid4())
    now = _now_iso()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO memos
                (id, title, source_kind, source_filename, status,
                 transcript_revision, language_override, created_at, updated_at)
            VALUES (?, ?, 'upload', ?, ?, ?, ?, ?, ?)
            """,
            (memo_id, title, source_filename, status, transcript_revision, language_override, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return memo_id


def _insert_job(
    db_path: Path,
    memo_id: str,
    job_id: str | None = None,
    status: str = "completed",
    stage: str | None = None,
    progress: float = 1.0,
    attempt_count: int = 1,
    hotwords: str | None = None,
    enable_diarization: bool = False,
    error_code: str | None = None,
    error_message: str | None = None,
) -> str:
    job_id = job_id or str(uuid.uuid4())
    now = _now_iso()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO jobs
                (id, memo_id, job_type, status, stage, progress,
                 attempt_count, hotwords, enable_diarization,
                 error_code, error_message, created_at, started_at, finished_at)
            VALUES (?, ?, 'transcribe', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                memo_id,
                status,
                stage,
                progress,
                attempt_count,
                hotwords,
                enable_diarization,
                error_code,
                error_message,
                now,
                now if status != "queued" else None,
                now if status in ("completed", "failed", "cancelled") else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def _count_jobs(db_path: Path, memo_id: str) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM jobs WHERE memo_id = ?", (memo_id,)).fetchone()
        return row[0]
    finally:
        conn.close()


def _get_latest_job(db_path: Path, memo_id: str) -> dict:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE memo_id = ? ORDER BY created_at DESC LIMIT 1",
            (memo_id,),
        ).fetchone()
        col_names = [
            desc[0]
            for desc in conn.execute(
                "SELECT * FROM jobs WHERE memo_id = ? ORDER BY created_at DESC LIMIT 1",
                (memo_id,),
            ).description
        ]
        return dict(zip(col_names, row))
    finally:
        conn.close()


def _get_memo(db_path: Path, memo_id: str) -> dict:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
        col_names = [desc[0] for desc in conn.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).description]
        return dict(zip(col_names, row))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


class TestReprocessService:
    """Tests for the reprocess_memo service function."""

    @pytest.fixture()
    def tmp_db(self, tmp_path: Path) -> Path:
        db_path = tmp_path / "test.db"
        run_migrations(db_path)
        return db_path

    def test_reprocess_completed_memo_creates_new_job(self, tmp_db: Path):
        """Reprocess creates a new queued job for a completed memo."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed", transcript_revision=1)
        _insert_job(tmp_db, memo_id, status="completed", progress=1.0)

        new_job = jobs_service.reprocess_memo(tmp_db, memo_id)

        assert new_job is not None
        assert new_job["status"] == "queued"
        assert new_job["memo_id"] == memo_id
        assert new_job["attempt_count"] == 2

    def test_reprocess_increments_attempt_count(self, tmp_db: Path):
        """Reprocess increments attempt_count from the latest job."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed", transcript_revision=1)
        _insert_job(tmp_db, memo_id, status="completed", attempt_count=3)

        new_job = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert new_job["attempt_count"] == 4

    def test_reprocess_preserves_hotwords(self, tmp_db: Path):
        """Reprocess carries forward hotwords from the previous job."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed", transcript_revision=1)
        _insert_job(tmp_db, memo_id, status="completed", hotwords="meeting,agenda")

        new_job = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert new_job["hotwords"] == "meeting,agenda"

    def test_reprocess_preserves_diarization_setting(self, tmp_db: Path):
        """Reprocess carries forward enable_diarization from the previous job."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed", transcript_revision=1)
        _insert_job(tmp_db, memo_id, status="completed", enable_diarization=True)

        new_job = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert new_job["enable_diarization"] == 1  # SQLite stores bool as int

    def test_reprocess_updates_memo_status_to_queued(self, tmp_db: Path):
        """Reprocess updates memo status to 'queued'."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed", transcript_revision=1)
        _insert_job(tmp_db, memo_id, status="completed")

        jobs_service.reprocess_memo(tmp_db, memo_id)

        memo = _get_memo(tmp_db, memo_id)
        assert memo["status"] == "queued"

    def test_reprocess_resets_transcript_revision(self, tmp_db: Path):
        """Reprocess resets transcript_revision to 0 (will be set to 1 on completion)."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed", transcript_revision=3)
        _insert_job(tmp_db, memo_id, status="completed")

        jobs_service.reprocess_memo(tmp_db, memo_id)

        memo = _get_memo(tmp_db, memo_id)
        assert memo["transcript_revision"] == 0

    def test_reprocess_active_job_returns_none(self, tmp_db: Path):
        """Reprocess of a memo with an active job returns None."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="transcribing", transcript_revision=0)
        _insert_job(tmp_db, memo_id, status="transcribing")

        result = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert result is None

    def test_reprocess_nonexistent_memo_returns_none(self, tmp_db: Path):
        """Reprocess of a non-existent memo returns None."""
        from app.services import jobs as jobs_service

        result = jobs_service.reprocess_memo(tmp_db, str(uuid.uuid4()))
        assert result is None

    def test_reprocess_memo_with_no_jobs_returns_none(self, tmp_db: Path):
        """Reprocess of a memo with no existing jobs returns None."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="completed")
        result = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert result is None

    def test_reprocess_failed_memo_creates_new_job(self, tmp_db: Path):
        """Reprocess works on failed memos too (like retry)."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="failed", transcript_revision=0)
        _insert_job(tmp_db, memo_id, status="failed", error_code="ASR_FAILED", error_message="test error")

        new_job = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert new_job is not None
        assert new_job["status"] == "queued"

    def test_reprocess_cancelled_memo_creates_new_job(self, tmp_db: Path):
        """Reprocess works on cancelled memos too (like retry)."""
        from app.services import jobs as jobs_service

        memo_id = _insert_memo(tmp_db, status="cancelled", transcript_revision=0)
        _insert_job(tmp_db, memo_id, status="cancelled")

        new_job = jobs_service.reprocess_memo(tmp_db, memo_id)
        assert new_job is not None
        assert new_job["status"] == "queued"


# ---------------------------------------------------------------------------
# API Endpoint tests (using TestClient)
# ---------------------------------------------------------------------------


class TestReprocessEndpoint:
    """Tests for POST /api/memos/{id}/reprocess API endpoint."""

    @pytest.fixture()
    def client(self, tmp_path: Path):
        from fastapi.testclient import TestClient

        from app.main import create_app

        with patch("app.core.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.data_dir = tmp_path
            settings.static_dir = tmp_path / "static"
            settings.db_path = tmp_path / "nanoscribe.db"
            mock_settings.return_value = settings

            # Run migrations
            run_migrations(tmp_path / "nanoscribe.db")

            # Patch module-level DATA_DIR in api.jobs so endpoints use tmp_path
            with patch("app.api.jobs.DATA_DIR", tmp_path):
                app = create_app()
                yield TestClient(app)

    def test_reprocess_completed_memo(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess creates new job for completed memo."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=1)
        _insert_job(db_path, memo_id, status="completed")

        response = client.post(f"/api/memos/{memo_id}/reprocess")

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "queued"
        assert data["memo_id"] == memo_id
        assert data["attempt_count"] == 2

    def test_reprocess_without_confirm_on_edited_transcript(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess returns 409 if transcript has been edited.

        transcript_revision > 1 means the user has edited the transcript.
        Without confirm=true, the endpoint must refuse to overwrite.
        """
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=3)
        _insert_job(db_path, memo_id, status="completed")

        response = client.post(f"/api/memos/{memo_id}/reprocess")

        assert response.status_code == 409
        assert "edited" in response.json()["detail"].lower() or "confirm" in response.json()["detail"].lower()

    def test_reprocess_with_confirm_on_edited_transcript(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess?confirm=true succeeds for edited transcript."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=3)
        _insert_job(db_path, memo_id, status="completed")

        response = client.post(f"/api/memos/{memo_id}/reprocess?confirm=true")

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "queued"

    def test_reprocess_no_confirm_needed_for_revision_1(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess succeeds without confirm for revision 1."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=1)
        _insert_job(db_path, memo_id, status="completed")

        response = client.post(f"/api/memos/{memo_id}/reprocess")

        assert response.status_code == 201

    def test_reprocess_not_found(self, client):
        """POST /api/memos/{id}/reprocess returns 404 for non-existent memo."""
        response = client.post(f"/api/memos/{uuid.uuid4()}/reprocess")
        assert response.status_code == 404

    def test_reprocess_active_job_returns_409(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess returns 409 if memo has active job."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="transcribing", transcript_revision=0)
        _insert_job(db_path, memo_id, status="transcribing")

        response = client.post(f"/api/memos/{memo_id}/reprocess")

        assert response.status_code == 409

    def test_reprocess_memo_status_updates_to_queued(self, client, tmp_path: Path):
        """After reprocess, memo status is 'queued'."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=1)
        _insert_job(db_path, memo_id, status="completed")

        client.post(f"/api/memos/{memo_id}/reprocess")

        memo = _get_memo(db_path, memo_id)
        assert memo["status"] == "queued"

    def test_reprocess_preserves_memo_metadata(self, client, tmp_path: Path):
        """Reprocess does not change title, source_kind, or source_filename."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=1, title="My Interview")
        _insert_job(db_path, memo_id, status="completed")

        client.post(f"/api/memos/{memo_id}/reprocess")

        memo = _get_memo(db_path, memo_id)
        assert memo["title"] == "My Interview"
        assert memo["source_kind"] == "upload"
        assert memo["source_filename"] == "test.wav"

    def test_reprocess_failed_memo(self, client, tmp_path: Path):
        """Reprocess works on failed memos."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="failed", transcript_revision=0)
        _insert_job(db_path, memo_id, status="failed", error_code="ASR_FAILED", error_message="test")

        response = client.post(f"/api/memos/{memo_id}/reprocess")

        assert response.status_code == 201

    def test_reprocess_cancelled_memo(self, client, tmp_path: Path):
        """Reprocess works on cancelled memos."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="cancelled", transcript_revision=0)
        _insert_job(db_path, memo_id, status="cancelled")

        response = client.post(f"/api/memos/{memo_id}/reprocess")

        assert response.status_code == 201

    def test_reprocess_creates_additional_job_row(self, client, tmp_path: Path):
        """Reprocess creates a new job row without removing old ones."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=1)
        _insert_job(db_path, memo_id, status="completed")

        assert _count_jobs(db_path, memo_id) == 1

        client.post(f"/api/memos/{memo_id}/reprocess")

        assert _count_jobs(db_path, memo_id) == 2

    def test_reprocess_with_confirm_false_rejects_edited(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess?confirm=false rejects edited transcript."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=2)
        _insert_job(db_path, memo_id, status="completed")

        response = client.post(f"/api/memos/{memo_id}/reprocess?confirm=false")

        assert response.status_code == 409

    def test_reprocess_with_confirm_1_succeeds_edited(self, client, tmp_path: Path):
        """POST /api/memos/{id}/reprocess?confirm=1 succeeds for edited transcript."""
        db_path = tmp_path / "nanoscribe.db"
        memo_id = _insert_memo(db_path, status="completed", transcript_revision=2)
        _insert_job(db_path, memo_id, status="completed")

        response = client.post(f"/api/memos/{memo_id}/reprocess?confirm=1")

        assert response.status_code == 201
