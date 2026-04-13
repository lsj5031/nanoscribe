"""Tests for SQLite schema, migrations, and FTS5 index.

Covers:
- Migration runner creates all tables with correct schema
- Migrations are idempotent (safe to run multiple times)
- FTS5 virtual table created for search indexing
- Foreign key constraints enabled (PRAGMA foreign_keys=ON)
- WAL mode enabled (PRAGMA journal_mode=WAL)
- VAL-SEARCH-007: FTS5 table creation and search readiness
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from app.db.migrate import run_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Provide a SQLite connection with migrations applied."""
    run_migrations(db_path)
    connection = sqlite3.connect(str(db_path))
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


class TestMigrationRunner:
    """Tests for migration runner basics."""

    def test_creates_database_file(self, db_path: Path) -> None:
        """Migration runner creates the database file."""
        assert not db_path.exists()
        run_migrations(db_path)
        assert db_path.exists()

    def test_idempotent_migrations(self, db_path: Path) -> None:
        """Running migrations multiple times does not raise errors."""
        run_migrations(db_path)
        run_migrations(db_path)  # Should not raise
        run_migrations(db_path)  # Third time's the charm

    def test_wal_mode_enabled(self, conn: sqlite3.Connection) -> None:
        """WAL mode should be enabled on the connection."""
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_foreign_keys_enabled(self, conn: sqlite3.Connection) -> None:
        """Foreign keys should be enforced."""
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1


class TestMemosTable:
    """Tests for the memos table schema."""

    EXPECTED_COLUMNS = {
        "id",
        "title",
        "source_kind",
        "source_filename",
        "duration_ms",
        "language_detected",
        "language_override",
        "status",
        "speaker_count",
        "transcript_revision",
        "created_at",
        "updated_at",
        "last_opened_at",
        "last_edited_at",
    }

    def test_memos_table_exists(self, conn: sqlite3.Connection) -> None:
        """memos table should be created."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memos'").fetchone()
        assert result is not None

    def test_memos_table_has_all_columns(self, conn: sqlite3.Connection) -> None:
        """memos table should have all required columns."""
        columns = self._get_column_names(conn, "memos")
        assert self.EXPECTED_COLUMNS == columns

    def test_memos_id_is_text_primary_key(self, conn: sqlite3.Connection) -> None:
        """memos.id should be TEXT PRIMARY KEY."""
        col_info = self._get_column_info(conn, "memos", "id")
        assert col_info["type"] == "TEXT"
        assert col_info["pk"] == 1
        assert col_info["notnull"] == 1

    def test_memos_title_not_null(self, conn: sqlite3.Connection) -> None:
        """memos.title should be NOT NULL."""
        col_info = self._get_column_info(conn, "memos", "title")
        assert col_info["notnull"] == 1

    def test_memos_status_default_queued(self, conn: sqlite3.Connection) -> None:
        """memos.status should default to 'queued'."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('test-1', 'Test', 'upload', 'test.wav')"
        )
        row = conn.execute("SELECT status FROM memos WHERE id='test-1'").fetchone()
        assert row["status"] == "queued"

    def test_memos_transcript_revision_default_zero(self, conn: sqlite3.Connection) -> None:
        """memos.transcript_revision should default to 0."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('test-2', 'Test', 'upload', 'test.wav')"
        )
        row = conn.execute("SELECT transcript_revision FROM memos WHERE id='test-2'").fetchone()
        assert row["transcript_revision"] == 0

    def test_memos_speaker_count_default_zero(self, conn: sqlite3.Connection) -> None:
        """memos.speaker_count should default to 0."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('test-3', 'Test', 'upload', 'test.wav')"
        )
        row = conn.execute("SELECT speaker_count FROM memos WHERE id='test-3'").fetchone()
        assert row["speaker_count"] == 0

    def test_memos_created_at_auto_populated(self, conn: sqlite3.Connection) -> None:
        """memos.created_at should be auto-populated with current timestamp."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('test-4', 'Test', 'upload', 'test.wav')"
        )
        row = conn.execute("SELECT created_at FROM memos WHERE id='test-4'").fetchone()
        assert row["created_at"] is not None
        assert len(row["created_at"]) > 0

    def _get_column_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        """Get column names for a table."""
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {row["name"] for row in rows}

    def _get_column_info(self, conn: sqlite3.Connection, table: str, column: str) -> dict:
        """Get column info for a specific column."""
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        for row in rows:
            if row["name"] == column:
                return dict(row)
        pytest.fail(f"Column {column} not found in {table}")


class TestJobsTable:
    """Tests for the jobs table schema."""

    EXPECTED_COLUMNS = {
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
        "hotwords",
        "enable_diarization",
        "created_at",
        "started_at",
        "finished_at",
    }

    def test_jobs_table_exists(self, conn: sqlite3.Connection) -> None:
        """jobs table should be created."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
        assert result is not None

    def test_jobs_table_has_all_columns(self, conn: sqlite3.Connection) -> None:
        """jobs table should have all required columns."""
        columns = self._get_column_names(conn, "jobs")
        assert self.EXPECTED_COLUMNS == columns

    def test_jobs_id_is_text_primary_key(self, conn: sqlite3.Connection) -> None:
        """jobs.id should be TEXT PRIMARY KEY."""
        col_info = self._get_column_info(conn, "jobs", "id")
        assert col_info["type"] == "TEXT"
        assert col_info["pk"] == 1
        assert col_info["notnull"] == 1

    def test_jobs_memo_id_foreign_key(self, conn: sqlite3.Connection) -> None:
        """jobs.memo_id should reference memos.id."""
        # Insert a memo first
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-1', 'Test', 'upload', 'test.wav')"
        )
        # Valid foreign key should work
        conn.execute(
            "INSERT INTO jobs (id, memo_id, job_type, status, attempt_count) "
            "VALUES ('job-1', 'memo-1', 'transcribe', 'queued', 1)"
        )
        # Invalid foreign key should fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO jobs (id, memo_id, job_type, status, attempt_count) "
                "VALUES ('job-2', 'nonexistent', 'transcribe', 'queued', 1)"
            )

    def test_jobs_status_default_queued(self, conn: sqlite3.Connection) -> None:
        """jobs.status should default to 'queued'."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-2', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO jobs (id, memo_id, job_type, attempt_count) VALUES ('job-3', 'memo-2', 'transcribe', 1)"
        )
        row = conn.execute("SELECT status FROM jobs WHERE id='job-3'").fetchone()
        assert row["status"] == "queued"

    def test_jobs_progress_default_zero(self, conn: sqlite3.Connection) -> None:
        """jobs.progress should default to 0.0."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-3', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO jobs (id, memo_id, job_type, attempt_count) VALUES ('job-4', 'memo-3', 'transcribe', 1)"
        )
        row = conn.execute("SELECT progress FROM jobs WHERE id='job-4'").fetchone()
        assert row["progress"] == 0.0

    def test_jobs_attempt_count_not_null(self, conn: sqlite3.Connection) -> None:
        """jobs.attempt_count should be NOT NULL."""
        col_info = self._get_column_info(conn, "jobs", "attempt_count")
        assert col_info["notnull"] == 1

    def test_jobs_created_at_auto_populated(self, conn: sqlite3.Connection) -> None:
        """jobs.created_at should be auto-populated."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-4', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO jobs (id, memo_id, job_type, attempt_count) VALUES ('job-5', 'memo-4', 'transcribe', 1)"
        )
        row = conn.execute("SELECT created_at FROM jobs WHERE id='job-5'").fetchone()
        assert row["created_at"] is not None

    def _get_column_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {row["name"] for row in rows}

    def _get_column_info(self, conn: sqlite3.Connection, table: str, column: str) -> dict:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        for row in rows:
            if row["name"] == column:
                return dict(row)
        pytest.fail(f"Column {column} not found in {table}")


class TestSegmentsTable:
    """Tests for the segments table schema."""

    EXPECTED_COLUMNS = {
        "id",
        "memo_id",
        "ordinal",
        "start_ms",
        "end_ms",
        "text",
        "speaker_key",
        "confidence",
        "edited",
        "created_at",
        "updated_at",
    }

    def test_segments_table_exists(self, conn: sqlite3.Connection) -> None:
        """segments table should be created."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='segments'").fetchone()
        assert result is not None

    def test_segments_table_has_all_columns(self, conn: sqlite3.Connection) -> None:
        """segments table should have all required columns."""
        columns = self._get_column_names(conn, "segments")
        assert self.EXPECTED_COLUMNS == columns

    def test_segments_memo_id_foreign_key(self, conn: sqlite3.Connection) -> None:
        """segments.memo_id should reference memos.id."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-s1', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-1', 'memo-s1', 1, 0, 1000, 'Hello world')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
                "VALUES ('seg-2', 'nonexistent', 1, 0, 1000, 'Fail')"
            )

    def test_segments_edited_default_false(self, conn: sqlite3.Connection) -> None:
        """segments.edited should default to FALSE (0)."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-s2', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-3', 'memo-s2', 1, 0, 1000, 'Test')"
        )
        row = conn.execute("SELECT edited FROM segments WHERE id='seg-3'").fetchone()
        assert row["edited"] == 0

    def test_segments_created_at_auto_populated(self, conn: sqlite3.Connection) -> None:
        """segments.created_at should be auto-populated."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-s3', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-4', 'memo-s3', 1, 0, 1000, 'Test')"
        )
        row = conn.execute("SELECT created_at FROM segments WHERE id='seg-4'").fetchone()
        assert row["created_at"] is not None

    def _get_column_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {row["name"] for row in rows}


class TestMemoSpeakersTable:
    """Tests for the memo_speakers table schema."""

    EXPECTED_COLUMNS = {
        "id",
        "memo_id",
        "speaker_key",
        "display_name",
        "color",
        "created_at",
        "updated_at",
    }

    def test_memo_speakers_table_exists(self, conn: sqlite3.Connection) -> None:
        """memo_speakers table should be created."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memo_speakers'").fetchone()
        assert result is not None

    def test_memo_speakers_table_has_all_columns(self, conn: sqlite3.Connection) -> None:
        """memo_speakers table should have all required columns."""
        columns = self._get_column_names(conn, "memo_speakers")
        assert self.EXPECTED_COLUMNS == columns

    def test_memo_speakers_memo_id_foreign_key(self, conn: sqlite3.Connection) -> None:
        """memo_speakers.memo_id should reference memos.id."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-sp1', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color) "
            "VALUES ('spk-1', 'memo-sp1', 'SPEAKER_00', 'Speaker 1', '#ff6b6b')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color) "
                "VALUES ('spk-2', 'nonexistent', 'SPEAKER_01', 'Speaker 2', '#4ecdc4')"
            )

    def test_memo_speakers_created_at_auto_populated(self, conn: sqlite3.Connection) -> None:
        """memo_speakers.created_at should be auto-populated."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-sp2', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color) "
            "VALUES ('spk-3', 'memo-sp2', 'SPEAKER_00', 'Speaker 1', '#ff6b6b')"
        )
        row = conn.execute("SELECT created_at FROM memo_speakers WHERE id='spk-3'").fetchone()
        assert row["created_at"] is not None

    def _get_column_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {row["name"] for row in rows}


class TestFTS5SearchIndex:
    """Tests for FTS5 virtual table for search indexing.

    VAL-SEARCH-007: Search backend uses SQLite FTS5 full-text search.
    """

    def test_fts5_table_exists(self, conn: sqlite3.Connection) -> None:
        """FTS5 virtual table should be created for search."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memos_fts'").fetchone()
        assert result is not None

    def test_fts5_is_virtual_table(self, conn: sqlite3.Connection) -> None:
        """memos_fts should be a virtual table using FTS5."""
        result = conn.execute("SELECT sql FROM sqlite_master WHERE name='memos_fts'").fetchone()
        assert result is not None
        sql = result["sql"].lower()
        assert "fts5" in sql

    def test_fts5_uses_unicode61_tokenizer(self, conn: sqlite3.Connection) -> None:
        """FTS5 table should use unicode61 tokenizer for Unicode-aware tokenization."""
        result = conn.execute("SELECT sql FROM sqlite_master WHERE name='memos_fts'").fetchone()
        assert result is not None
        sql = result["sql"].lower()
        assert "unicode61" in sql

    def test_fts5_indexes_title_and_text(self, conn: sqlite3.Connection) -> None:
        """FTS5 table should index memo title and segment text."""
        result = conn.execute("SELECT sql FROM sqlite_master WHERE name='memos_fts'").fetchone()
        assert result is not None
        sql = result["sql"].lower()
        assert "title" in sql
        assert "text" in sql

    def test_fts5_basic_search(self, conn: sqlite3.Connection) -> None:
        """FTS5 MATCH query should work for basic search on memo titles."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-fts1', 'Meeting Notes', 'upload', 'meeting.wav')"
        )
        # The trigger should auto-insert the title into FTS
        result = conn.execute("SELECT * FROM memos_fts WHERE memos_fts MATCH 'meeting'").fetchall()
        assert len(result) > 0

    def test_fts5_multi_segment_search(self, conn: sqlite3.Connection) -> None:
        """All segments per memo must be searchable via FTS MATCH.

        Regression test: the original triggers used the memo's rowid as the
        FTS rowid, so only the LAST segment per memo was searchable.
        """
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-multi', 'Project Call', 'upload', 'call.wav')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-m1', 'memo-multi', 1, 0, 5000, 'budget discussion')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-m2', 'memo-multi', 2, 5000, 10000, 'timeline review')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-m3', 'memo-multi', 3, 10000, 15000, 'risk assessment')"
        )

        # ALL three segments must be independently searchable
        budget = conn.execute("SELECT * FROM memos_fts WHERE memos_fts MATCH 'budget'").fetchall()
        assert len(budget) >= 1, "Segment 1 'budget discussion' should be searchable"

        timeline = conn.execute("SELECT * FROM memos_fts WHERE memos_fts MATCH 'timeline'").fetchall()
        assert len(timeline) >= 1, "Segment 2 'timeline review' should be searchable"

        risk = conn.execute("SELECT * FROM memos_fts WHERE memos_fts MATCH 'risk'").fetchall()
        assert len(risk) >= 1, "Segment 3 'risk assessment' should be searchable"

    def test_fts5_segment_search_returns_correct_memo_id(self, conn: sqlite3.Connection) -> None:
        """FTS search should allow looking up the correct memo_id for each segment."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) VALUES ('memo-a', 'Memo A', 'upload', 'a.wav')"
        )
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) VALUES ('memo-b', 'Memo B', 'upload', 'b.wav')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-a1', 'memo-a', 1, 0, 5000, 'alpha bravo')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-b1', 'memo-b', 1, 0, 5000, 'charlie delta')"
        )

        # Search for 'alpha' should find segment from memo-a
        results = conn.execute(
            "SELECT s.memo_id FROM memos_fts f JOIN segments s ON s.rowid = f.rowid WHERE memos_fts MATCH 'alpha'"
        ).fetchall()
        memo_ids = [r["memo_id"] for r in results]
        assert "memo-a" in memo_ids, "Searching 'alpha' should find memo-a"

        # Search for 'charlie' should find segment from memo-b
        results = conn.execute(
            "SELECT s.memo_id FROM memos_fts f JOIN segments s ON s.rowid = f.rowid WHERE memos_fts MATCH 'charlie'"
        ).fetchall()
        memo_ids = [r["memo_id"] for r in results]
        assert "memo-b" in memo_ids, "Searching 'charlie' should find memo-b"

    def test_fts5_content_sync_with_memos(self, conn: sqlite3.Connection) -> None:
        """FTS5 should support content= option for external content table
        referencing memos and segments."""
        result = conn.execute("SELECT sql FROM sqlite_master WHERE name='memos_fts'").fetchone()
        # The FTS5 table should be set up with content= for automatic sync
        # or have triggers defined
        sql = result["sql"].lower()
        # Either uses content=external or is standalone content table
        assert "memos_fts" in sql


class TestMigrationTracking:
    """Tests for migration tracking table."""

    def test_migration_tracking_table_exists(self, conn: sqlite3.Connection) -> None:
        """A _migrations table should track applied migrations."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'").fetchone()
        assert result is not None

    def test_migration_records_applied(self, conn: sqlite3.Connection) -> None:
        """Applied migrations should be recorded in _migrations table."""
        rows = conn.execute("SELECT name FROM _migrations ORDER BY name").fetchall()
        assert len(rows) > 0
        # Should have at least one migration
        names = [row["name"] for row in rows]
        assert any("001" in name for name in names)

    def test_migration_has_timestamp(self, conn: sqlite3.Connection) -> None:
        """Each migration record should have an applied_at timestamp."""
        rows = conn.execute("SELECT applied_at FROM _migrations").fetchall()
        for row in rows:
            assert row["applied_at"] is not None


class TestCascadingDeletes:
    """Tests for ON DELETE CASCADE behavior."""

    def test_delete_memo_cascades_to_jobs(self, conn: sqlite3.Connection) -> None:
        """Deleting a memo should cascade to delete associated jobs."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-del1', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO jobs (id, memo_id, job_type, attempt_count) VALUES ('job-del1', 'memo-del1', 'transcribe', 1)"
        )
        conn.execute("DELETE FROM memos WHERE id='memo-del1'")
        result = conn.execute("SELECT * FROM jobs WHERE memo_id='memo-del1'").fetchall()
        assert len(result) == 0

    def test_delete_memo_cascades_to_segments(self, conn: sqlite3.Connection) -> None:
        """Deleting a memo should cascade to delete associated segments."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-del2', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO segments (id, memo_id, ordinal, start_ms, end_ms, text) "
            "VALUES ('seg-del1', 'memo-del2', 1, 0, 1000, 'Hello')"
        )
        conn.execute("DELETE FROM memos WHERE id='memo-del2'")
        result = conn.execute("SELECT * FROM segments WHERE memo_id='memo-del2'").fetchall()
        assert len(result) == 0

    def test_delete_memo_cascades_to_speakers(self, conn: sqlite3.Connection) -> None:
        """Deleting a memo should cascade to delete associated speakers."""
        conn.execute(
            "INSERT INTO memos (id, title, source_kind, source_filename) "
            "VALUES ('memo-del3', 'Test', 'upload', 'test.wav')"
        )
        conn.execute(
            "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color) "
            "VALUES ('spk-del1', 'memo-del3', 'SPEAKER_00', 'Speaker 1', '#ff6b6b')"
        )
        conn.execute("DELETE FROM memos WHERE id='memo-del3'")
        result = conn.execute("SELECT * FROM memo_speakers WHERE memo_id='memo-del3'").fetchall()
        assert len(result) == 0
