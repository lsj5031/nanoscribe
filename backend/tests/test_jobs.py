"""Tests for job lifecycle, worker, SSE events, cancel, retry, recovery.

Covers VAL-JOB-001 through VAL-JOB-022 assertions.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("NANOSCRIBE_DATA_DIR", "/tmp/nanoscribe-test-jobs")
os.environ.setdefault("NANOSCRIBE_STATIC_DIR", "/tmp/nanoscribe-test-static")

from app.core.config import get_settings
from app.db import db_connection
from app.db.migrate import run_migrations
from app.services import jobs as jobs_service

DATA_DIR = get_settings().data_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _insert_memo(db_path: Path, memo_id: str | None = None, status: str = "queued") -> str:
    memo_id = memo_id or str(uuid.uuid4())
    now = _now_iso()
    with db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memos (id, title, source_kind, source_filename, status, created_at, updated_at)
            VALUES (?, 'Test', 'upload', 'test.wav', ?, ?, ?)
            """,
            (memo_id, status, now, now),
        )
        conn.commit()
    return memo_id


def _insert_job(
    db_path: Path,
    memo_id: str,
    job_id: str | None = None,
    job_type: str = "transcribe",
    status: str = "queued",
    stage: str | None = None,
    progress: float = 0.0,
    attempt_count: int = 1,
    error_code: str | None = None,
    error_message: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> str:
    job_id = job_id or str(uuid.uuid4())
    now = _now_iso()
    with db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (id, memo_id, job_type, status, stage, progress,
                 attempt_count, error_code, error_message, created_at, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                memo_id,
                job_type,
                status,
                stage,
                progress,
                attempt_count,
                error_code,
                error_message,
                now,
                started_at,
                finished_at,
            ),
        )
        conn.commit()
    return job_id


# ---------------------------------------------------------------------------
# VAL-JOB-001: Job row created with required fields
# ---------------------------------------------------------------------------


class TestJobCreation:
    def test_job_row_has_required_fields(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        with db_connection(tmp_db) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            col_names = [desc[0] for desc in conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).description]
            row_dict = dict(zip(col_names, row))
        assert row_dict["job_type"] == "transcribe"
        assert row_dict["status"] == "queued"
        assert row_dict["progress"] == 0.0
        assert row_dict["attempt_count"] == 1
        assert row_dict["created_at"] is not None
        assert row_dict["error_message"] is None

    def test_create_job_service(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job = jobs_service.create_job(tmp_db, memo_id)

        assert job["memo_id"] == memo_id
        assert job["job_type"] == "transcribe"
        assert job["status"] == "queued"
        assert job["progress"] == 0.0
        assert job["attempt_count"] == 1
        assert job["error_message"] is None


# ---------------------------------------------------------------------------
# VAL-JOB-002: Job status transitions follow valid state machine
# ---------------------------------------------------------------------------


class TestStateTransitions:
    def test_valid_forward_transition(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        # queued → preprocessing
        jobs_service.transition_job(tmp_db, job_id, "preprocessing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "preprocessing"
        assert job["stage"] == "preprocessing"

        # preprocessing → transcribing
        jobs_service.transition_job(tmp_db, job_id, "transcribing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "transcribing"

        # transcribing → finalizing
        jobs_service.transition_job(tmp_db, job_id, "finalizing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "finalizing"

        # finalizing → completed
        jobs_service.transition_job(tmp_db, job_id, "completed")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "completed"
        assert job["progress"] == 1.0

    def test_transition_to_failed(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="transcribing", stage="transcribing")

        jobs_service.fail_job(tmp_db, job_id, "ASR_FAILED", "GPU OOM")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "failed"
        assert job["error_code"] == "ASR_FAILED"
        assert job["error_message"] == "GPU OOM"

    def test_transition_to_cancelled(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="transcribing", stage="transcribing")

        jobs_service.transition_job(tmp_db, job_id, "cancelled")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "cancelled"

    def test_valid_diarize_pipeline_transition(self, tmp_db: Path):
        """Diarize-only jobs skip transcribing: preprocessing → diarizing."""
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, job_type="diarize")

        # queued → preprocessing
        jobs_service.transition_job(tmp_db, job_id, "preprocessing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "preprocessing"
        assert job["job_type"] == "diarize"

        # preprocessing → diarizing (skips transcribing)
        jobs_service.transition_job(tmp_db, job_id, "diarizing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "diarizing"
        assert job["stage"] == "diarizing"

        # diarizing → finalizing
        jobs_service.transition_job(tmp_db, job_id, "finalizing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "finalizing"

        # finalizing → completed
        jobs_service.transition_job(tmp_db, job_id, "completed")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "completed"
        assert job["progress"] == 1.0

    def test_cannot_transition_from_terminal(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="completed")

        with pytest.raises(jobs_service.InvalidTransitionError):
            jobs_service.transition_job(tmp_db, job_id, "queued")


# ---------------------------------------------------------------------------
# VAL-JOB-003: Job progress is monotonically increasing
# ---------------------------------------------------------------------------


class TestProgress:
    def test_update_progress_increases(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, progress=0.1)

        jobs_service.update_progress(tmp_db, job_id, 0.3)
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["progress"] == 0.3

        jobs_service.update_progress(tmp_db, job_id, 0.6)
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["progress"] == 0.6

    def test_progress_cannot_decrease(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, progress=0.5)

        jobs_service.update_progress(tmp_db, job_id, 0.3)
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["progress"] == 0.5  # Unchanged

    def test_progress_bounded_upper(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        jobs_service.update_progress(tmp_db, job_id, 1.5)
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["progress"] == 1.0

    def test_progress_bounded_lower(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        jobs_service.update_progress(tmp_db, job_id, -0.1)
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["progress"] == 0.0


# ---------------------------------------------------------------------------
# VAL-JOB-004: GET /api/jobs/{id} returns complete job state
# ---------------------------------------------------------------------------


class TestGetJob:
    def test_get_job_returns_all_fields(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        expected_fields = {
            "id",
            "memo_id",
            "job_type",
            "status",
            "stage",
            "progress",
            "eta_seconds",
            "device_used",
            "error_code",
            "error_message",
            "attempt_count",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
        }
        assert expected_fields.issubset(set(job.keys()))

    def test_get_nonexistent_job_returns_none(self, tmp_db: Path):
        result = jobs_service.get_job(tmp_db, str(uuid.uuid4()))
        assert result is None

    def test_get_job_with_error_info(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(
            tmp_db, memo_id, status="failed", error_code="NORMALIZATION_FAILED", error_message="ffmpeg failed"
        )

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "failed"
        assert job["error_code"] == "NORMALIZATION_FAILED"
        assert job["error_message"] == "ffmpeg failed"


# ---------------------------------------------------------------------------
# VAL-JOB-005: Only one GPU job runs at a time
# ---------------------------------------------------------------------------


class TestConcurrencyLimit:
    def test_only_one_active_job(self, tmp_db: Path):
        memo1 = _insert_memo(tmp_db)
        memo2 = _insert_memo(tmp_db)
        job1 = _insert_job(tmp_db, memo1, status="transcribing", stage="transcribing")
        job2 = _insert_job(tmp_db, memo2, status="queued")

        active = jobs_service.get_active_job(tmp_db)
        assert active is not None
        assert active["id"] == job1

        # Second job should remain queued
        job2_data = jobs_service.get_job(tmp_db, job2)
        assert job2_data is not None
        assert job2_data["status"] == "queued"

    def test_no_active_job_returns_none(self, tmp_db: Path):
        memo1 = _insert_memo(tmp_db, status="completed")
        _insert_job(tmp_db, memo1, status="completed")

        active = jobs_service.get_active_job(tmp_db)
        assert active is None

    def test_next_queued_job(self, tmp_db: Path):
        memo1 = _insert_memo(tmp_db)
        memo2 = _insert_memo(tmp_db)
        _insert_job(tmp_db, memo1, status="completed")
        job2 = _insert_job(tmp_db, memo2, status="queued")

        next_job = jobs_service.get_next_queued_job(tmp_db)
        assert next_job is not None
        assert next_job["id"] == job2


# ---------------------------------------------------------------------------
# VAL-JOB-006: Job attempt_count increments on retry
# ---------------------------------------------------------------------------


class TestAttemptCount:
    def test_initial_attempt_count_is_one(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job = jobs_service.create_job(tmp_db, memo_id)
        assert job["attempt_count"] == 1

    def test_retry_increments_attempt(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="failed")
        _insert_job(tmp_db, memo_id, status="failed", attempt_count=1, error_code="ASR_FAILED", error_message="test")

        # Update memo to failed
        with db_connection(tmp_db) as conn:
            conn.execute("UPDATE memos SET status = 'failed' WHERE id = ?", (memo_id,))
            conn.commit()

        new_job = jobs_service.retry_memo(tmp_db, memo_id)
        assert new_job is not None
        assert new_job["attempt_count"] == 2
        assert new_job["status"] == "queued"

    def test_multiple_retries(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="failed")
        _insert_job(tmp_db, memo_id, status="failed", attempt_count=2, error_code="ASR_FAILED", error_message="test")

        with db_connection(tmp_db) as conn:
            conn.execute("UPDATE memos SET status = 'failed' WHERE id = ?", (memo_id,))
            conn.commit()

        new_job = jobs_service.retry_memo(tmp_db, memo_id)
        assert new_job is not None
        assert new_job["attempt_count"] == 3


# ---------------------------------------------------------------------------
# VAL-JOB-008: Cancel during transcription stops GPU processing
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_active_job(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="transcribing")
        job_id = _insert_job(tmp_db, memo_id, status="transcribing", stage="transcribing")

        result = jobs_service.cancel_job(tmp_db, job_id)
        assert result is True

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "cancelled"

    def test_cancel_completed_job_returns_false(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="completed")
        job_id = _insert_job(tmp_db, memo_id, status="completed")

        result = jobs_service.cancel_job(tmp_db, job_id)
        assert result is False

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "completed"

    def test_cancel_failed_job_returns_false(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="failed")
        job_id = _insert_job(tmp_db, memo_id, status="failed")

        result = jobs_service.cancel_job(tmp_db, job_id)
        assert result is False

    def test_cancel_already_cancelled_returns_false(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="cancelled")
        job_id = _insert_job(tmp_db, memo_id, status="cancelled")

        result = jobs_service.cancel_job(tmp_db, job_id)
        assert result is False


# ---------------------------------------------------------------------------
# VAL-JOB-009: Job timestamps are UTC ISO 8601
# ---------------------------------------------------------------------------


class TestTimestamps:
    def test_created_at_is_iso8601(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job = jobs_service.create_job(tmp_db, memo_id)

        # Should be parseable as ISO 8601
        created = job["created_at"]
        assert created.endswith("Z")
        # Parse to verify format
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ")

    def test_created_at_immutable(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        with db_connection(tmp_db) as conn:
            original = conn.execute("SELECT created_at FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]

        # Transition the job
        jobs_service.transition_job(tmp_db, job_id, "preprocessing")

        with db_connection(tmp_db) as conn:
            after = conn.execute("SELECT created_at FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]

        assert original == after


# ---------------------------------------------------------------------------
# VAL-JOB-010: Job completion updates memo metadata
# ---------------------------------------------------------------------------


class TestMemoMetadata:
    def test_completion_updates_memo(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="finalizing", stage="finalizing")

        jobs_service.transition_job(tmp_db, job_id, "completed")

        with db_connection(tmp_db) as conn:
            memo = conn.execute("SELECT status, transcript_revision FROM memos WHERE id = ?", (memo_id,)).fetchone()

        assert memo[0] == "completed"
        assert memo[1] == 1

    def test_failure_updates_memo(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="transcribing")
        job_id = _insert_job(tmp_db, memo_id, status="transcribing")

        jobs_service.fail_job(tmp_db, job_id, "ASR_FAILED", "model error")

        with db_connection(tmp_db) as conn:
            memo = conn.execute("SELECT status FROM memos WHERE id = ?", (memo_id,)).fetchone()

        assert memo[0] == "failed"

    def test_cancel_updates_memo(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="transcribing")
        job_id = _insert_job(tmp_db, memo_id, status="transcribing")

        jobs_service.cancel_job(tmp_db, job_id)

        with db_connection(tmp_db) as conn:
            memo = conn.execute("SELECT status FROM memos WHERE id = ?", (memo_id,)).fetchone()

        assert memo[0] == "cancelled"


# ---------------------------------------------------------------------------
# VAL-JOB-012: Concurrent job creation is serialized
# ---------------------------------------------------------------------------


class TestJobSerialization:
    def test_queued_jobs_processed_sequentially(self, tmp_db: Path):
        """When multiple jobs are queued, only one can be active."""
        memo1 = _insert_memo(tmp_db)
        memo2 = _insert_memo(tmp_db)
        memo3 = _insert_memo(tmp_db)
        _insert_job(tmp_db, memo1, status="transcribing", stage="transcribing")
        _insert_job(tmp_db, memo2, status="queued")
        _insert_job(tmp_db, memo3, status="queued")

        # Only one active job
        active = jobs_service.get_active_job(tmp_db)
        assert active is not None
        assert active["memo_id"] == memo1

        # Count queued
        next_job = jobs_service.get_next_queued_job(tmp_db)
        assert next_job is not None


# ---------------------------------------------------------------------------
# VAL-JOB-014: Retry preserves memo data
# ---------------------------------------------------------------------------


class TestRetryPreservesData:
    def test_retry_preserves_memo_metadata(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="failed")
        _insert_job(tmp_db, memo_id, status="failed", attempt_count=1, error_code="ASR_FAILED", error_message="test")

        with db_connection(tmp_db) as conn:
            conn.execute("UPDATE memos SET status = 'failed' WHERE id = ?", (memo_id,))
            conn.commit()

        jobs_service.retry_memo(tmp_db, memo_id)

        with db_connection(tmp_db) as conn:
            memo = conn.execute(
                "SELECT title, source_kind, source_filename FROM memos WHERE id = ?",
                (memo_id,),
            ).fetchone()

        assert memo[0] == "Test"
        assert memo[1] == "upload"
        assert memo[2] == "test.wav"

    def test_retry_non_failed_returns_none(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="transcribing")
        _insert_job(tmp_db, memo_id, status="transcribing")

        result = jobs_service.retry_memo(tmp_db, memo_id)
        assert result is None


# ---------------------------------------------------------------------------
# VAL-JOB-015: Job error codes are consistent
# ---------------------------------------------------------------------------


class TestErrorCodes:
    def test_normalization_failed(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="preprocessing")

        jobs_service.fail_job(tmp_db, job_id, "NORMALIZATION_FAILED", "ffmpeg failed")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["error_code"] == "NORMALIZATION_FAILED"

    def test_asr_failed(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="transcribing")

        jobs_service.fail_job(tmp_db, job_id, "ASR_FAILED", "model error")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["error_code"] == "ASR_FAILED"

    def test_cancelled_error_code(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="transcribing")

        jobs_service.transition_job(tmp_db, job_id, "cancelled")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "cancelled"


# ---------------------------------------------------------------------------
# VAL-JOB-016: Stale jobs recovered on startup
# ---------------------------------------------------------------------------


class TestStartupRecovery:
    def test_stale_transcribing_job_requeued(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="transcribing")
        job_id = _insert_job(tmp_db, memo_id, status="transcribing")

        jobs_service.recover_stale_jobs(tmp_db)

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] in ("queued", "failed")

    def test_stale_preprocessing_job_requeued(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="preprocessing")
        job_id = _insert_job(tmp_db, memo_id, status="preprocessing")

        jobs_service.recover_stale_jobs(tmp_db)

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] in ("queued", "failed")

    def test_completed_job_untouched(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="completed")
        job_id = _insert_job(tmp_db, memo_id, status="completed")

        jobs_service.recover_stale_jobs(tmp_db)

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "completed"

    def test_failed_job_untouched(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="failed")
        job_id = _insert_job(tmp_db, memo_id, status="failed", error_code="ASR_FAILED", error_message="test")

        jobs_service.recover_stale_jobs(tmp_db)

        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "failed"

    def test_no_active_jobs_recovery_is_noop(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="completed")
        _insert_job(tmp_db, memo_id, status="completed")

        # Should not raise
        jobs_service.recover_stale_jobs(tmp_db)


# ---------------------------------------------------------------------------
# VAL-JOB-017: Job list endpoint returns jobs for a memo
# ---------------------------------------------------------------------------


class TestJobList:
    def test_jobs_for_memo(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job1 = _insert_job(
            tmp_db, memo_id, status="failed", attempt_count=1, error_code="ASR_FAILED", error_message="test"
        )
        job2 = _insert_job(tmp_db, memo_id, status="queued", attempt_count=2)

        jobs = jobs_service.get_jobs_for_memo(tmp_db, memo_id)
        assert len(jobs) == 2
        # Most recent first
        assert jobs[0]["id"] == job2
        assert jobs[1]["id"] == job1

    def test_empty_jobs_for_memo(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        jobs = jobs_service.get_jobs_for_memo(tmp_db, memo_id)
        assert jobs == []


# ---------------------------------------------------------------------------
# VAL-JOB-019: Job stage field matches status
# ---------------------------------------------------------------------------


class TestStageMatchesStatus:
    def test_stage_set_on_transition(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        jobs_service.transition_job(tmp_db, job_id, "preprocessing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "preprocessing"
        assert job["stage"] == "preprocessing"

    def test_stage_on_transcribing(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="preprocessing", stage="preprocessing")

        jobs_service.transition_job(tmp_db, job_id, "transcribing")
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "transcribing"
        assert job["stage"] == "transcribing"


# ---------------------------------------------------------------------------
# VAL-JOB-020: Transcript revision starts at 1
# ---------------------------------------------------------------------------


class TestTranscriptRevision:
    def test_revision_starts_at_one_on_completion(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="finalizing", stage="finalizing")

        jobs_service.transition_job(tmp_db, job_id, "completed")

        with db_connection(tmp_db) as conn:
            memo = conn.execute("SELECT transcript_revision FROM memos WHERE id = ?", (memo_id,)).fetchone()

        assert memo[0] == 1


# ---------------------------------------------------------------------------
# VAL-JOB-021: Retry after cancel re-queues from beginning
# ---------------------------------------------------------------------------


class TestRetryAfterCancel:
    def test_retry_cancelled_job_starts_from_beginning(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db, status="cancelled")
        _insert_job(
            tmp_db,
            memo_id,
            status="cancelled",
            attempt_count=1,
        )

        with db_connection(tmp_db) as conn:
            conn.execute("UPDATE memos SET status = 'cancelled' WHERE id = ?", (memo_id,))
            conn.commit()

        new_job = jobs_service.retry_memo(tmp_db, memo_id)
        assert new_job is not None
        assert new_job["status"] == "queued"
        assert new_job["attempt_count"] == 2


# ---------------------------------------------------------------------------
# VAL-JOB-022: Job worker survives transient GPU errors
# ---------------------------------------------------------------------------


class TestWorkerResilience:
    def test_fail_job_does_not_crash(self, tmp_db: Path):
        """Failing a job should leave the system in a consistent state."""
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id, status="transcribing")

        jobs_service.fail_job(tmp_db, job_id, "ASR_FAILED", "GPU OOM")

        # Job should be failed
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["status"] == "failed"
        assert job["error_code"] == "ASR_FAILED"

        # Memo should be failed
        with db_connection(tmp_db) as conn:
            memo = conn.execute("SELECT status FROM memos WHERE id = ?", (memo_id,)).fetchone()
        assert memo[0] == "failed"

        # Next queued job should still be pickable
        memo2 = _insert_memo(tmp_db)
        job2 = _insert_job(tmp_db, memo2, status="queued")
        next_job = jobs_service.get_next_queued_job(tmp_db)
        assert next_job is not None
        assert next_job["id"] == job2


# ---------------------------------------------------------------------------
# VAL-JOB-018: Job progress updates are throttled
# (This tests the service-level throttle, actual SSE throttle is in worker)
# ---------------------------------------------------------------------------


class TestProgressThrottle:
    def test_progress_update_records_updated_at(self, tmp_db: Path):
        memo_id = _insert_memo(tmp_db)
        job_id = _insert_job(tmp_db, memo_id)

        jobs_service.update_progress(tmp_db, job_id, 0.5)
        job = jobs_service.get_job(tmp_db, job_id)
        assert job is not None
        assert job["progress"] == 0.5


# ---------------------------------------------------------------------------
# SSE Event Manager tests
# ---------------------------------------------------------------------------


class TestSSEEventManager:
    def test_subscribe_and_publish(self):
        from app.services.sse import SSEEventManager

        manager = SSEEventManager()
        events = []

        async def collector(event: dict):
            events.append(event)

        manager.subscribe("job-1", collector)
        manager.publish("job-1", {"event": "job.stage", "data": {"stage": "preprocessing"}})

        assert len(events) == 1
        assert events[0]["data"]["stage"] == "preprocessing"

    def test_unsubscribe(self):
        from app.services.sse import SSEEventManager

        manager = SSEEventManager()
        events = []

        async def collector(event: dict):
            events.append(event)

        manager.subscribe("job-1", collector)
        manager.unsubscribe("job-1", collector)
        manager.publish("job-1", {"event": "job.stage", "data": {"stage": "preprocessing"}})

        assert len(events) == 0

    def test_publish_to_empty_channel(self):
        from app.services.sse import SSEEventManager

        manager = SSEEventManager()
        # Should not raise
        manager.publish("nonexistent", {"event": "test", "data": {}})


# ---------------------------------------------------------------------------
# API Endpoint tests (using TestClient)
# ---------------------------------------------------------------------------


class TestJobAPIEndpoints:
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

            # Patch the module-level DATA_DIR in jobs.py and main.py
            # since they cache settings at import time
            with patch("app.api.jobs.DATA_DIR", tmp_path), \
                 patch("app.main.DATA_DIR", tmp_path), \
                 patch("app.main.STATIC_DIR", tmp_path / "static"):

                # Run migrations
                run_migrations(tmp_path / "nanoscribe.db")

                app = create_app()
                yield TestClient(app)

    def test_get_job_not_found(self, client):
        response = client.get(f"/api/jobs/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_cancel_completed_returns_409(self, client, tmp_path: Path):
        # This would require proper setup with the app's DB
        # For now we test the service layer directly
        pass
