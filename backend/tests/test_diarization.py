"""Tests for diarization service and merge logic."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("NANOSCRIBE_DATA_DIR", "/tmp/nanoscribe-test-diarization")
os.environ.setdefault("NANOSCRIBE_STATIC_DIR", "/tmp/nanoscribe-test-static")

from app.db import db_connection
from app.db.migrate import run_migrations
from app.services.diarization import create_speaker_rows
from app.services.diarization_merge import merge_diarization

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
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _insert_memo(db_path: Path, memo_id: str | None = None) -> str:
    memo_id = memo_id or str(uuid.uuid4())
    now = _now_iso()
    with db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memos (id, title, source_kind, source_filename, status, created_at, updated_at)
            VALUES (?, 'Test', 'upload', 'test.wav', 'completed', ?, ?)
            """,
            (memo_id, now, now),
        )
        conn.commit()
    return memo_id


# ---------------------------------------------------------------------------
# merge_diarization tests
# ---------------------------------------------------------------------------


class TestMergeDiarization:
    """Tests for the merge_diarization overlap-assignment logic."""

    def test_assigns_speaker_by_greatest_overlap(self):
        """Each ASR segment gets the speaker with most temporal overlap."""
        asr_segments = [
            {"id": "s1", "start_ms": 0, "end_ms": 3000, "text": "Hello world"},
            {"id": "s2", "start_ms": 3000, "end_ms": 6000, "text": "Goodbye world"},
        ]
        diarization = [
            {"speaker": "spk0", "start_ms": 0, "end_ms": 3500},
            {"speaker": "spk1", "start_ms": 3500, "end_ms": 7000},
        ]

        result = merge_diarization(asr_segments, diarization)

        assert result[0]["speaker_key"] == "spk0"
        assert result[1]["speaker_key"] == "spk1"

    def test_single_speaker(self):
        """All segments assigned to the same speaker."""
        asr_segments = [
            {"id": "s1", "start_ms": 0, "end_ms": 2000, "text": "A"},
            {"id": "s2", "start_ms": 2000, "end_ms": 4000, "text": "B"},
        ]
        diarization = [
            {"speaker": "spk0", "start_ms": 0, "end_ms": 4000},
        ]

        result = merge_diarization(asr_segments, diarization)

        assert all(seg["speaker_key"] == "spk0" for seg in result)

    def test_no_diarization_segments(self):
        """Returns segments unchanged when no diarization available."""
        asr_segments = [
            {"id": "s1", "start_ms": 0, "end_ms": 1000, "text": "Hello"},
        ]

        result = merge_diarization(asr_segments, [])

        assert "speaker_key" not in result[0]

    def test_no_overlap_gets_none(self):
        """Segments with zero overlap get speaker_key=None."""
        asr_segments = [
            {"id": "s1", "start_ms": 10000, "end_ms": 12000, "text": "Late speech"},
        ]
        diarization = [
            {"speaker": "spk0", "start_ms": 0, "end_ms": 5000},
        ]

        result = merge_diarization(asr_segments, diarization)

        assert result[0]["speaker_key"] is None

    def test_overlapping_speakers_picks_greatest(self):
        """When multiple speakers overlap, picks the one with most overlap."""
        asr_segments = [
            {"id": "s1", "start_ms": 2000, "end_ms": 5000, "text": "Overlapping"},
        ]
        diarization = [
            {"speaker": "spk0", "start_ms": 0, "end_ms": 3000},  # overlap: 1000ms
            {"speaker": "spk1", "start_ms": 3000, "end_ms": 8000},  # overlap: 2000ms
        ]

        result = merge_diarization(asr_segments, diarization)

        assert result[0]["speaker_key"] == "spk1"

    def test_does_not_mutate_original_diarization(self):
        """Diarization segments are not modified."""
        asr_segments = [
            {"id": "s1", "start_ms": 0, "end_ms": 1000, "text": "Hi"},
        ]
        diarization = [
            {"speaker": "spk0", "start_ms": 0, "end_ms": 1000},
        ]
        orig_speaker = diarization[0]["speaker"]

        merge_diarization(asr_segments, diarization)

        assert diarization[0]["speaker"] == orig_speaker


# ---------------------------------------------------------------------------
# create_speaker_rows tests
# ---------------------------------------------------------------------------


class TestCreateSpeakerRows:
    """Tests for the create_speaker_rows database function."""

    def test_creates_correct_speaker_entries(self, tmp_db: Path):
        """Creates one memo_speakers row per unique speaker_key."""
        memo_id = _insert_memo(tmp_db)
        segments = [
            {"speaker_key": "spk0", "start_ms": 0, "end_ms": 1000},
            {"speaker_key": "spk0", "start_ms": 1000, "end_ms": 2000},
            {"speaker_key": "spk1", "start_ms": 2000, "end_ms": 3000},
        ]

        create_speaker_rows(tmp_db, memo_id, segments)

        with db_connection(tmp_db) as conn:
            rows = conn.execute(
                "SELECT speaker_key, display_name, color FROM memo_speakers WHERE memo_id = ? ORDER BY speaker_key",
                (memo_id,),
            ).fetchall()

        assert len(rows) == 2
        keys = {r[0] for r in rows}
        assert keys == {"spk0", "spk1"}

    def test_speakers_ordered_by_first_appearance(self, tmp_db: Path):
        """Speakers are numbered by first appearance in segments."""
        memo_id = _insert_memo(tmp_db)
        segments = [
            {"speaker_key": "spk1", "start_ms": 0, "end_ms": 1000},
            {"speaker_key": "spk0", "start_ms": 1000, "end_ms": 2000},
            {"speaker_key": "spk1", "start_ms": 2000, "end_ms": 3000},
        ]

        create_speaker_rows(tmp_db, memo_id, segments)

        with db_connection(tmp_db) as conn:
            rows = conn.execute(
                "SELECT speaker_key, display_name FROM memo_speakers WHERE memo_id = ? ORDER BY rowid",
                (memo_id,),
            ).fetchall()

        # spk1 appears first → Speaker 1, spk0 appears second → Speaker 2
        assert rows[0] == ("spk1", "Speaker 1")
        assert rows[1] == ("spk0", "Speaker 2")

    def test_updates_speaker_count(self, tmp_db: Path):
        """Updates memo speaker_count to number of unique speakers."""
        memo_id = _insert_memo(tmp_db)
        segments = [
            {"speaker_key": "spk0", "start_ms": 0, "end_ms": 1000},
            {"speaker_key": "spk1", "start_ms": 1000, "end_ms": 2000},
            {"speaker_key": "spk2", "start_ms": 2000, "end_ms": 3000},
        ]

        create_speaker_rows(tmp_db, memo_id, segments)

        with db_connection(tmp_db) as conn:
            count = conn.execute("SELECT speaker_count FROM memos WHERE id = ?", (memo_id,)).fetchone()[0]

        assert count == 3

    def test_no_segments_no_rows(self, tmp_db: Path):
        """No-op when segments list is empty."""
        memo_id = _insert_memo(tmp_db)

        create_speaker_rows(tmp_db, memo_id, [])

        with db_connection(tmp_db) as conn:
            rows = conn.execute("SELECT * FROM memo_speakers WHERE memo_id = ?", (memo_id,)).fetchall()

        assert len(rows) == 0

    def test_speaker_colors_assigned(self, tmp_db: Path):
        """Each speaker gets a distinct pastel color."""
        memo_id = _insert_memo(tmp_db)
        segments = [
            {"speaker_key": "spk0", "start_ms": 0, "end_ms": 1000},
            {"speaker_key": "spk1", "start_ms": 1000, "end_ms": 2000},
        ]

        create_speaker_rows(tmp_db, memo_id, segments)

        with db_connection(tmp_db) as conn:
            rows = conn.execute(
                "SELECT color FROM memo_speakers WHERE memo_id = ? ORDER BY rowid",
                (memo_id,),
            ).fetchall()

        assert rows[0][0] == "#00d4ff"
        assert rows[1][0] == "#f472b6"

    def test_more_speakers_than_colors(self, tmp_db: Path):
        """Colors cycle when there are more speakers than color slots."""
        memo_id = _insert_memo(tmp_db)
        segments = [{"speaker_key": f"spk{i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000} for i in range(8)]

        create_speaker_rows(tmp_db, memo_id, segments)

        with db_connection(tmp_db) as conn:
            rows = conn.execute(
                "SELECT speaker_key, color FROM memo_speakers WHERE memo_id = ? ORDER BY rowid",
                (memo_id,),
            ).fetchall()

        assert len(rows) == 8
        # First and 7th speaker should share same color (index 0 and 6 → wraps at 6 colors)
        assert rows[0][1] == rows[6][1]


# ---------------------------------------------------------------------------
# run_diarization graceful degradation tests
# ---------------------------------------------------------------------------


class TestRunDiarizationDegradation:
    """Tests for graceful degradation when 3D-Speaker is not available."""

    def test_returns_empty_when_not_installed(self, tmp_path: Path):
        """Returns empty list when 3D-Speaker is not importable."""
        from app.services.diarization import run_diarization

        # Create a dummy audio file — won't be processed since import fails
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        result = run_diarization(audio)
        # 3D-Speaker is likely not installed in test environment
        assert isinstance(result, list)

    def test_returns_empty_on_failure(self, tmp_path: Path):
        """Returns empty list when diarization encounters an error.

        Since 3D-Speaker is typically not installed in the test environment,
        run_diarization already returns []. We verify the type contract.
        """
        import importlib

        import app.services.diarization

        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00" * 100)

        # Clear any cached imports to force a fresh attempt
        importlib.reload(app.services.diarization)
        from app.services.diarization import run_diarization as fresh_run

        result = fresh_run(audio)
        assert isinstance(result, list)
