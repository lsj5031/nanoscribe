"""Job lifecycle service — state transitions, cancel, retry, recovery.

Handles all VAL-JOB-xxx assertions:
  - Job creation with required fields (VAL-JOB-001)
  - State machine transitions (VAL-JOB-002)
  - Monotonically increasing progress (VAL-JOB-003)
  - Job snapshot queries (VAL-JOB-004)
  - One GPU job at a time (VAL-JOB-005)
  - Attempt count tracking (VAL-JOB-006)
  - Cancellation (VAL-JOB-007/008)
  - ISO 8601 timestamps (VAL-JOB-009)
  - Memo status sync (VAL-JOB-010/011)
  - Startup recovery (VAL-JOB-016)
  - Error codes (VAL-JOB-015)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import db_connection, in_placeholders

# Terminal states — no transitions allowed out of these
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})

# Active (non-terminal) states
ACTIVE_STATES = frozenset({"queued", "preprocessing", "transcribing", "diarizing", "finalizing"})

# Valid transitions: from_state → set of allowed to_states
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"preprocessing", "failed", "cancelled"}),
    "preprocessing": frozenset({"transcribing", "diarizing", "failed", "cancelled"}),
    "transcribing": frozenset({"diarizing", "finalizing", "failed", "cancelled"}),
    "diarizing": frozenset({"finalizing", "failed", "cancelled"}),
    "finalizing": frozenset({"completed", "failed", "cancelled"}),
}


class InvalidTransitionError(Exception):
    """Raised when a job state transition is not allowed."""

    pass


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def create_job(
    db_path: str | Path,
    memo_id: str,
    attempt_count: int = 1,
    hotwords: str | None = None,
    enable_diarization: bool = False,
) -> dict[str, Any]:
    """Create a new job row for a memo.

    VAL-JOB-001: Job row created with all required fields.
    """
    job_id = str(uuid.uuid4())
    now = _now_iso()
    with db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (id, memo_id, job_type, status, stage, progress,
                 attempt_count, hotwords, enable_diarization, created_at)
            VALUES (?, ?, 'transcribe', 'queued', NULL, 0.0, ?, ?, ?, ?)
            """,
            (job_id, memo_id, attempt_count, hotwords, enable_diarization, now),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        col_names = [desc[0] for desc in conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).description]
        return dict(zip(col_names, row))


def get_job(db_path: str | Path, job_id: str) -> dict[str, Any] | None:
    """Get a job by ID.

    VAL-JOB-004: Returns complete job state or None if not found.
    """
    with db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        col_names = [desc[0] for desc in conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).description]
        return dict(zip(col_names, row))


def get_jobs_for_memo(db_path: str | Path, memo_id: str) -> list[dict[str, Any]]:
    """Get all jobs for a memo, ordered by created_at descending.

    VAL-JOB-017: Returns jobs in reverse chronological order.
    """
    with db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE memo_id = ? ORDER BY created_at DESC",
            (memo_id,),
        ).fetchall()
        if not rows:
            return []
        col_names = [
            desc[0]
            for desc in conn.execute(
                "SELECT * FROM jobs WHERE memo_id = ? ORDER BY created_at DESC", (memo_id,)
            ).description
        ]
        return [dict(zip(col_names, row)) for row in rows]


def get_active_job(db_path: str | Path) -> dict[str, Any] | None:
    """Get the currently active (non-terminal) job, if any.

    Returns the first job found in an active state.
    VAL-JOB-005: There should only be one active GPU job at a time.
    """
    with db_connection(db_path) as conn:
        ph = in_placeholders(len(ACTIVE_STATES))
        row = conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({ph}) ORDER BY created_at ASC LIMIT 1",
            list(ACTIVE_STATES),
        ).fetchone()
        if row is None:
            return None
        col_names = [
            desc[0]
            for desc in conn.execute(
                f"SELECT * FROM jobs WHERE status IN ({ph}) ORDER BY created_at ASC LIMIT 1",
                list(ACTIVE_STATES),
            ).description
        ]
        return dict(zip(col_names, row))


def get_next_queued_job(db_path: str | Path) -> dict[str, Any] | None:
    """Get the next queued job to process (oldest first / FIFO).

    Returns None if no active job is running and no queued jobs exist.
    """
    with db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1").fetchone()
        if row is None:
            return None
        col_names = [
            desc[0]
            for desc in conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).description
        ]
        return dict(zip(col_names, row))


def transition_job(db_path: str | Path, job_id: str, new_status: str) -> dict[str, Any]:
    """Transition a job to a new status.

    VAL-JOB-002: Enforces valid state machine transitions.
    Updates stage, started_at/finished_at, progress, and memo status.
    """
    with db_connection(db_path) as conn:
        job = conn.execute("SELECT status, memo_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise InvalidTransitionError(f"Job {job_id} not found")

        current_status = job[0]
        memo_id = job[1]

        # Terminal states cannot transition
        if current_status in TERMINAL_STATES:
            raise InvalidTransitionError(
                f"Cannot transition job {job_id} from terminal state '{current_status}' to '{new_status}'"
            )

        # Validate transition (except for terminal targets which are always valid from active states)
        if new_status not in TERMINAL_STATES:
            allowed = VALID_TRANSITIONS.get(current_status, frozenset())
            if new_status not in allowed:
                raise InvalidTransitionError(f"Invalid transition: {current_status} → {new_status}")

        now = _now_iso()

        # Build update — column names are hardcoded constants, not user input
        updates: list[str] = ["status = ?", "stage = ?", "updated_at = ?"]
        params: list[Any] = [new_status, new_status, now]

        # Set started_at on first active transition
        if new_status in ACTIVE_STATES and new_status != "queued":
            updates.append("started_at = COALESCE(started_at, ?)")
            params.append(now)

        # Set finished_at on terminal states
        if new_status in TERMINAL_STATES:
            updates.append("finished_at = ?")
            params.append(now)

        # Set progress to 1.0 on completion
        if new_status == "completed":
            updates.append("progress = 1.0")

        params.append(job_id)
        conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
            params,
        )

        # Update memo status to match job status
        _update_memo_status(conn, memo_id, new_status, now)

        conn.commit()

        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        col_names = [desc[0] for desc in conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).description]
        return dict(zip(col_names, row))


def fail_job(
    db_path: str | Path,
    job_id: str,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    """Mark a job as failed with error details.

    VAL-JOB-006/015: Stores error_code and error_message.
    VAL-JOB-022: Worker survives — job is marked failed, next job can proceed.
    """
    with db_connection(db_path) as conn:
        now = _now_iso()
        conn.execute(
            """
            UPDATE jobs SET
                status = 'failed',
                stage = 'failed',
                error_code = ?,
                error_message = ?,
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (error_code, error_message, now, now, job_id),
        )

        # Get memo_id for status sync
        memo_id = conn.execute("SELECT memo_id FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]
        _update_memo_status(conn, memo_id, "failed", now)

        conn.commit()

        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        col_names = [desc[0] for desc in conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).description]
        return dict(zip(col_names, row))


def update_progress(db_path: str | Path, job_id: str, progress: float) -> None:
    """Update job progress. Clamps to [0.0, 1.0] and never decreases.

    VAL-JOB-003: Progress is monotonically increasing and bounded.
    """
    with db_connection(db_path) as conn:
        current = conn.execute("SELECT progress FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if current is None:
            return

        current_progress = current[0]
        # Clamp and enforce monotonicity
        new_progress = max(0.0, min(1.0, progress))
        if new_progress < current_progress:
            return  # Don't decrease

        now = _now_iso()
        conn.execute(
            "UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?",
            (new_progress, now, job_id),
        )
        conn.commit()


def cancel_job(db_path: str | Path, job_id: str) -> bool:
    """Cancel a job. Returns True if cancelled, False if already terminal.

    VAL-JOB-004/005: Cancel transitions to cancelled state.
    VAL-TRANS-005: Cancel of terminal job returns False (API returns 409).
    """
    with db_connection(db_path) as conn:
        job = conn.execute("SELECT status, memo_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            return False

        current_status = job[0]
        memo_id = job[1]

        if current_status in TERMINAL_STATES:
            return False

        now = _now_iso()
        conn.execute(
            """
            UPDATE jobs SET
                status = 'cancelled',
                stage = 'cancelled',
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, job_id),
        )

        _update_memo_status(conn, memo_id, "cancelled", now)
        conn.commit()
        return True


def retry_memo(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Retry a failed or cancelled memo by creating a new job.

    VAL-TRANS-007: Creates new job with incremented attempt_count.
    VAL-TRANS-008: Returns None if memo has an active job (API returns 409).
    VAL-JOB-014: Preserves memo metadata.
    VAL-JOB-021: Retry after cancel re-queues from beginning.
    """
    with db_connection(db_path) as conn:
        # Get the latest job for this memo
        latest_job = conn.execute(
            "SELECT status, attempt_count, hotwords, enable_diarization "
            "FROM jobs WHERE memo_id = ? ORDER BY created_at DESC LIMIT 1",
            (memo_id,),
        ).fetchone()

        if latest_job is None:
            return None

        latest_status = latest_job[0]

        # Only retry if latest job is terminal and not completed
        if latest_status not in ("failed", "cancelled"):
            return None

        attempt_count = latest_job[0 + 1]  # attempt_count column
        hotwords = latest_job[0 + 2]
        enable_diarization = latest_job[0 + 3]

        new_attempt = attempt_count + 1

    new_job = create_job(
        db_path, memo_id, attempt_count=new_attempt, hotwords=hotwords, enable_diarization=enable_diarization
    )

    # Update memo status to queued
    with db_connection(db_path) as conn:
        now = _now_iso()
        conn.execute(
            "UPDATE memos SET status = 'queued', updated_at = ? WHERE id = ?",
            (now, memo_id),
        )
        conn.commit()

    return new_job


def reprocess_memo(db_path: str | Path, memo_id: str) -> dict[str, Any] | None:
    """Reprocess a memo by creating a new transcription job.

    Unlike retry (which only works on failed/cancelled), reprocess works on
    any memo with a terminal job (including completed). This lets users
    re-transcribe with updated settings or after model updates.

    Returns the new job dict, or None if:
    - memo has no existing jobs
    - memo has an active (non-terminal) job

    The caller is responsible for checking transcript_revision before calling
    this function (to prevent silent overwrite of user edits).
    """
    with db_connection(db_path) as conn:
        # Get the latest job for this memo
        latest_job = conn.execute(
            "SELECT status, attempt_count, hotwords, enable_diarization "
            "FROM jobs WHERE memo_id = ? ORDER BY created_at DESC LIMIT 1",
            (memo_id,),
        ).fetchone()

        if latest_job is None:
            return None

        latest_status = latest_job[0]

        # Cannot reprocess if an active job is running
        if latest_status in ACTIVE_STATES:
            return None

        attempt_count = latest_job[1]
        hotwords = latest_job[2]
        enable_diarization = latest_job[3]

        new_attempt = attempt_count + 1

    new_job = create_job(
        db_path, memo_id, attempt_count=new_attempt, hotwords=hotwords, enable_diarization=enable_diarization
    )

    # Update memo status to queued and reset transcript_revision
    with db_connection(db_path) as conn:
        now = _now_iso()
        conn.execute(
            "UPDATE memos SET status = 'queued', transcript_revision = 0, updated_at = ? WHERE id = ?",
            (now, memo_id),
        )
        conn.commit()

    return new_job


def recover_stale_jobs(db_path: str | Path) -> int:
    """Recover stale active jobs on startup.

    VAL-JOB-016: Stale jobs (preprocessing, transcribing, diarizing, finalizing)
    are requeued. Queued jobs are left as-is.
    """
    # States that indicate a job was interrupted mid-processing
    stale_states = {"preprocessing", "transcribing", "diarizing", "finalizing"}
    with db_connection(db_path) as conn:
        ph = in_placeholders(len(stale_states))
        stale_jobs = conn.execute(
            f"SELECT id, memo_id FROM jobs WHERE status IN ({ph})",
            list(stale_states),
        ).fetchall()

        if not stale_jobs:
            return 0

        now = _now_iso()
        count = 0
        for job_id, memo_id in stale_jobs:
            # Requeue the stale job
            conn.execute(
                """
                UPDATE jobs SET
                    status = 'queued',
                    stage = NULL,
                    progress = 0.0,
                    started_at = NULL,
                    error_code = 'RECOVERED',
                    error_message = 'Job interrupted by server restart',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
            _update_memo_status(conn, memo_id, "queued", now)
            count += 1

        conn.commit()
        return count


def _update_memo_status(conn, memo_id: str, status: str, now: str) -> None:
    """Update memo status and relevant timestamps to match job status.

    VAL-JOB-010/011/012: Memo status mirrors job status.
    """
    # Column names are hardcoded constants, not user input
    updates = ["status = ?", "updated_at = ?"]
    params: list[Any] = [status, now]

    # On completion, set transcript_revision to 1 (VAL-JOB-020)
    if status == "completed":
        updates.append("transcript_revision = 1")
        updates.append("last_edited_at = ?")
        params.append(now)

    params.append(memo_id)
    conn.execute(
        f"UPDATE memos SET {', '.join(updates)} WHERE id = ?",
        params,
    )
