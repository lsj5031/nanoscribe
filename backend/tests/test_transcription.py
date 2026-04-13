"""Tests for FunASR transcription service.

Covers assertions:
  VAL-TRANS-009: FunASR model produces transcript segments with timestamps
  VAL-TRANS-010: Segments persisted to database and transcript JSON
  VAL-TRANS-013: VAD segments audio for efficient processing

Unit tests use mocked FunASR models. Integration test (marked with
@pytest.mark.integration) requires GPU and downloaded models.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("NANOSCRIBE_DATA_DIR", "/tmp/nanoscribe-test-transcription")
os.environ.setdefault("NANOSCRIBE_STATIC_DIR", "/tmp/nanoscribe-test-static")

from app.core.config import get_settings
from app.db import get_connection
from app.db.migrate import run_migrations
from app.services.transcription import (
    TranscriptionError,
    TranscriptionModels,
    _build_segments_from_timestamps,
    _build_segments_from_vad,
    _tokens_to_segment,
    get_models,
    is_model_ready,
    persist_transcript,
)

DATA_DIR = get_settings().data_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_models_singleton():
    """Reset the module-level models singleton between tests."""
    import app.services.transcription as mod

    old = mod._models
    mod._models = None
    yield
    mod._models = old


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


@pytest.fixture()
def memo_dir(tmp_path: Path) -> Path:
    """Create a memo directory with a dummy normalized.wav."""
    memo_id = str(uuid.uuid4())
    d = tmp_path / "memos" / memo_id
    d.mkdir(parents=True, exist_ok=True)
    # Write a tiny valid WAV header
    import wave

    with wave.open(str(d / "normalized.wav"), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 160)  # 10ms of silence
    return d


def _insert_memo_and_job(db_path: Path, memo_id: str) -> str:
    """Insert a minimal memo and job row for testing."""
    now = "2026-04-14T00:00:000000Z"
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO memos (id, title, source_kind, source_filename, status, created_at, updated_at)
            VALUES (?, 'Test', 'upload', 'test.wav', 'transcribing', ?, ?)
            """,
            (memo_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO jobs (id, memo_id, job_type, status, progress, attempt_count, created_at)
            VALUES (?, ?, 'transcribe', 'transcribing', 0.5, 1, ?)
            """,
            (str(uuid.uuid4()), memo_id, now),
        )
        conn.commit()
    finally:
        conn.close()
    return memo_id


# ---------------------------------------------------------------------------
# Token-to-segment conversion
# ---------------------------------------------------------------------------


class TestTokensToSegment:
    def test_empty_tokens_returns_none(self):
        assert _tokens_to_segment([]) is None

    def test_single_token(self):
        tokens = [{"token": "你", "start_time": 1.0, "end_time": 1.1, "score": 0.99}]
        result = _tokens_to_segment(tokens)
        assert result is not None
        assert result["text"] == "你"
        assert result["start_ms"] == 1000
        assert result["end_ms"] == 1100
        assert result["confidence"] == 0.99

    def test_multiple_tokens_with_confidence(self):
        tokens = [
            {"token": "你", "start_time": 1.0, "end_time": 1.1, "score": 0.95},
            {"token": "好", "start_time": 1.2, "end_time": 1.3, "score": 0.85},
        ]
        result = _tokens_to_segment(tokens)
        assert result is not None
        assert result["text"] == "你好"
        assert result["start_ms"] == 1000
        assert result["end_ms"] == 1300
        assert abs(result["confidence"] - 0.90) < 0.01

    def test_tokens_with_zero_score_excluded_from_confidence(self):
        tokens = [
            {"token": "你", "start_time": 1.0, "end_time": 1.1, "score": 0.99},
            {"token": "。", "start_time": 1.1, "end_time": 1.2, "score": 0.0},
        ]
        result = _tokens_to_segment(tokens)
        assert result is not None
        assert result["confidence"] == 0.99  # Only the non-zero score counted

    def test_all_zero_scores_defaults_to_one(self):
        tokens = [
            {"token": "，", "start_time": 0.5, "end_time": 0.6, "score": 0.0},
            {"token": "。", "start_time": 0.6, "end_time": 0.7, "score": 0.0},
        ]
        result = _tokens_to_segment(tokens)
        assert result is not None
        assert result["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Build segments from timestamps
# ---------------------------------------------------------------------------


class TestBuildSegmentsFromTimestamps:
    def test_empty_timestamps(self):
        assert _build_segments_from_timestamps([]) == []

    def test_single_sentence(self):
        timestamps = [
            {"token": "你", "start_time": 0.0, "end_time": 0.1, "score": 0.99},
            {"token": "好", "start_time": 0.1, "end_time": 0.2, "score": 0.98},
            {"token": "。", "start_time": 0.2, "end_time": 0.3, "score": 0.0},
        ]
        segments = _build_segments_from_timestamps(timestamps)
        assert len(segments) == 1
        assert segments[0]["text"] == "你好。"
        assert segments[0]["start_ms"] == 0
        assert segments[0]["end_ms"] == 300

    def test_multiple_sentences(self):
        timestamps = [
            {"token": "你", "start_time": 0.0, "end_time": 0.1, "score": 0.99},
            {"token": "好", "start_time": 0.1, "end_time": 0.2, "score": 0.98},
            {"token": "。", "start_time": 0.2, "end_time": 0.3, "score": 0.0},
            {"token": "世", "start_time": 1.0, "end_time": 1.1, "score": 0.95},
            {"token": "界", "start_time": 1.1, "end_time": 1.2, "score": 0.97},
            {"token": "！", "start_time": 1.2, "end_time": 1.3, "score": 0.0},
        ]
        segments = _build_segments_from_timestamps(timestamps)
        assert len(segments) == 2
        assert segments[0]["text"] == "你好。"
        assert segments[0]["start_ms"] == 0
        assert segments[0]["end_ms"] == 300
        assert segments[1]["text"] == "世界！"
        assert segments[1]["start_ms"] == 1000
        assert segments[1]["end_ms"] == 1300

    def test_trailing_tokens_without_punctuation(self):
        timestamps = [
            {"token": "你", "start_time": 0.0, "end_time": 0.1, "score": 0.99},
            {"token": "好", "start_time": 0.1, "end_time": 0.2, "score": 0.98},
            {"token": "。", "start_time": 0.2, "end_time": 0.3, "score": 0.0},
            {"token": "谢", "start_time": 1.0, "end_time": 1.1, "score": 0.95},
            {"token": "谢", "start_time": 1.1, "end_time": 1.2, "score": 0.96},
        ]
        segments = _build_segments_from_timestamps(timestamps)
        assert len(segments) == 2
        assert segments[1]["text"] == "谢谢"

    def test_english_punctuation(self):
        timestamps = [
            {"token": "Hello", "start_time": 0.0, "end_time": 0.5, "score": 0.99},
            {"token": ".", "start_time": 0.5, "end_time": 0.6, "score": 0.0},
            {"token": "World", "start_time": 1.0, "end_time": 1.5, "score": 0.98},
            {"token": "!", "start_time": 1.5, "end_time": 1.6, "score": 0.0},
        ]
        segments = _build_segments_from_timestamps(timestamps)
        assert len(segments) == 2
        assert segments[0]["text"] == "Hello."
        assert segments[1]["text"] == "World!"

    def test_segments_ordered_chronologically(self):
        timestamps = [
            {"token": "A", "start_time": 0.0, "end_time": 0.5, "score": 0.9},
            {"token": "。", "start_time": 0.5, "end_time": 0.6, "score": 0.0},
            {"token": "B", "start_time": 2.0, "end_time": 2.5, "score": 0.9},
            {"token": "。", "start_time": 2.5, "end_time": 2.6, "score": 0.0},
            {"token": "C", "start_time": 5.0, "end_time": 5.5, "score": 0.9},
            {"token": "。", "start_time": 5.5, "end_time": 5.6, "score": 0.0},
        ]
        segments = _build_segments_from_timestamps(timestamps)
        assert len(segments) == 3
        for i in range(len(segments) - 1):
            assert segments[i]["start_ms"] <= segments[i + 1]["start_ms"]


# ---------------------------------------------------------------------------
# Build segments from VAD
# ---------------------------------------------------------------------------


class TestBuildSegmentsFromVad:
    def test_empty_inputs(self):
        assert _build_segments_from_vad([], "text") == []
        assert _build_segments_from_vad([[0, 1000]], "") == []

    def test_single_vad_segment(self):
        segments = _build_segments_from_vad([[0, 5000]], "你好世界")
        assert len(segments) == 1
        assert segments[0]["text"] == "你好世界"
        assert segments[0]["start_ms"] == 0
        assert segments[0]["end_ms"] == 5000

    def test_multiple_vad_segments_proportional_split(self):
        segments = _build_segments_from_vad(
            [[0, 2000], [3000, 5000], [6000, 10000]],
            "你好世界测试文本",
        )
        assert len(segments) == 3
        # Each segment should have text
        for seg in segments:
            assert seg["text"].strip()
        # All text should be distributed
        combined = "".join(seg["text"] for seg in segments).replace(" ", "")
        assert combined == "你好世界测试文本"

    def test_zero_duration_vad(self):
        segments = _build_segments_from_vad([[1000, 1000], [2000, 2000]], "text")
        # Falls through to single segment covering full range
        assert len(segments) >= 1

    def test_remaining_text_appended_to_last(self):
        # More text than VAD time
        segments = _build_segments_from_vad([[0, 100]], "这是一个很长的文本")
        assert len(segments) >= 1
        # All text should be captured
        combined = "".join(seg["text"] for seg in segments).replace(" ", "")
        assert combined == "这是一个很长的文本"


# ---------------------------------------------------------------------------
# TranscriptionModels (mocked)
# ---------------------------------------------------------------------------


class TestTranscriptionModels:
    def test_not_loaded_initially(self):
        models = TranscriptionModels()
        assert not models.is_loaded
        assert models.device == "cpu"

    def test_transcribe_without_load_raises(self):
        models = TranscriptionModels()
        with pytest.raises(TranscriptionError, match="Models not loaded"):
            models.run_vad("/tmp/test.wav")

    def test_transcribe_raises_without_load(self):
        models = TranscriptionModels()
        with patch.object(models, "load", side_effect=TranscriptionError("FunASR is not installed")):
            with pytest.raises(TranscriptionError):
                models.transcribe("/tmp/test.wav")

    @patch("app.services.transcription._get_remote_code_path", return_value="/fake/model.py")
    def test_load_creates_models(self, _mock_rc):
        # Mock the AutoModel import
        with patch("app.services.transcription.TranscriptionModels._detect_device", return_value="cpu"):
            with patch("funasr.AutoModel") as mock_auto:
                models = TranscriptionModels()
                models.load()
                assert models.is_loaded
                # Should have called AutoModel 3 times: VAD, ASR, Punc
                assert mock_auto.call_count == 3

    @patch("app.services.transcription._get_remote_code_path", return_value="/fake/model.py")
    def test_load_idempotent(self, _mock_rc):
        with patch("app.services.transcription.TranscriptionModels._detect_device", return_value="cpu"):
            with patch("funasr.AutoModel") as mock_auto:
                models = TranscriptionModels()
                models.load()
                models.load()  # Second call should be a no-op
                assert mock_auto.call_count == 3  # Still only 3 calls

    def test_run_vad_with_mock(self):
        models = TranscriptionModels()
        models._vad_model = MagicMock()
        models._vad_model.generate.return_value = [{"key": "test", "value": [[100, 2000], [3000, 5000]]}]
        segments = models.run_vad("/tmp/test.wav")
        assert segments == [[100, 2000], [3000, 5000]]

    def test_run_vad_empty_result(self):
        models = TranscriptionModels()
        models._vad_model = MagicMock()
        models._vad_model.generate.return_value = [{"key": "test", "value": []}]
        segments = models.run_vad("/tmp/test.wav")
        assert segments == []

    def test_run_vad_error(self):
        models = TranscriptionModels()
        models._vad_model = MagicMock()
        models._vad_model.generate.side_effect = RuntimeError("GPU OOM")
        with pytest.raises(TranscriptionError, match="VAD processing failed"):
            models.run_vad("/tmp/test.wav")

    def test_run_asr_with_mock(self):
        models = TranscriptionModels()
        models._asr_model = MagicMock()
        models._asr_model.generate.return_value = [
            {
                "key": "test",
                "text": "你好世界。",
                "text_tn": "你好世界",
                "timestamps": [
                    {"token": "你", "start_time": 0.0, "end_time": 0.1, "score": 0.99},
                    {"token": "好", "start_time": 0.1, "end_time": 0.2, "score": 0.98},
                    {"token": "世", "start_time": 0.3, "end_time": 0.4, "score": 0.97},
                    {"token": "界", "start_time": 0.4, "end_time": 0.5, "score": 0.96},
                    {"token": "。", "start_time": 0.5, "end_time": 0.6, "score": 0.0},
                ],
            }
        ]
        result = models.run_asr("/tmp/test.wav")
        assert len(result) == 1
        assert "你好世界" in result[0]["text"]

    def test_run_asr_error(self):
        models = TranscriptionModels()
        models._asr_model = MagicMock()
        models._asr_model.generate.side_effect = RuntimeError("Model error")
        with pytest.raises(TranscriptionError, match="ASR processing failed"):
            models.run_asr("/tmp/test.wav")

    def test_run_punc_with_mock(self):
        models = TranscriptionModels()
        models._punc_model = MagicMock()
        models._punc_model.generate.return_value = [{"text": "你好，世界。"}]
        result = models.run_punc("你好世界")
        assert result == "你好，世界。"

    def test_run_punc_fallback_on_error(self):
        models = TranscriptionModels()
        models._punc_model = MagicMock()
        models._punc_model.generate.side_effect = RuntimeError("Punc failed")
        result = models.run_punc("你好世界")
        assert result == "你好世界"  # Returns original text

    def test_transcribe_full_pipeline_mock(self):
        models = TranscriptionModels()
        models._asr_model = MagicMock()
        models._vad_model = MagicMock()
        models._punc_model = MagicMock()

        # VAD returns speech segments
        models._vad_model.generate.return_value = [{"key": "test", "value": [[0, 2000], [3000, 5000]]}]

        # ASR returns text with timestamps
        models._asr_model.generate.return_value = [
            {
                "key": "test",
                "text": "你好世界。",
                "text_tn": "你好世界",
                "timestamps": [
                    {"token": "你", "start_time": 0.0, "end_time": 0.5, "score": 0.99},
                    {"token": "好", "start_time": 0.5, "end_time": 1.0, "score": 0.98},
                    {"token": "世", "start_time": 1.0, "end_time": 1.5, "score": 0.97},
                    {"token": "界", "start_time": 1.5, "end_time": 2.0, "score": 0.96},
                    {"token": "。", "start_time": 2.0, "end_time": 2.1, "score": 0.0},
                ],
            }
        ]

        result = models.transcribe("/tmp/test.wav")
        assert result["text"] == "你好世界。"
        assert len(result["segments"]) >= 1
        assert result["segments"][0]["start_ms"] >= 0
        assert result["segments"][0]["end_ms"] > result["segments"][0]["start_ms"]

    def test_transcribe_no_speech(self):
        models = TranscriptionModels()
        models._vad_model = MagicMock()
        models._vad_model.generate.return_value = [{"key": "test", "value": []}]

        # load() would normally set _asr_model, mock it as loaded
        models._asr_model = MagicMock()
        models._punc_model = MagicMock()

        result = models.transcribe("/tmp/test.wav")
        assert result["text"] == ""
        assert result["segments"] == []


# ---------------------------------------------------------------------------
# Persist transcript
# ---------------------------------------------------------------------------


class TestPersistTranscript:
    def test_persist_creates_files(self, tmp_path: Path, tmp_db: Path):
        memo_id = _insert_memo_and_job(tmp_db, str(uuid.uuid4()))

        # Override DATA_DIR for test
        memo_dir = tmp_path / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)

        raw_output = [{"key": "test", "text": "你好世界"}]
        segments = [{"start_ms": 0, "end_ms": 2000, "text": "你好世界", "confidence": 0.95}]

        with patch("app.services.transcription.DATA_DIR", tmp_path):
            persist_transcript(memo_id, raw_output, segments, tmp_db)

        # Check files
        assert (memo_dir / "transcript.raw.json").exists()
        assert (memo_dir / "transcript.final.json").exists()

        raw = json.loads((memo_dir / "transcript.raw.json").read_text())
        assert raw[0]["text"] == "你好世界"

        final = json.loads((memo_dir / "transcript.final.json").read_text())
        assert len(final) == 1
        assert final[0]["ordinal"] == 1
        assert final[0]["text"] == "你好世界"

    def test_persist_creates_db_rows(self, tmp_path: Path, tmp_db: Path):
        memo_id = _insert_memo_and_job(tmp_db, str(uuid.uuid4()))
        memo_dir = tmp_path / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)

        segments = [
            {"start_ms": 0, "end_ms": 1000, "text": "第一段", "confidence": 0.9},
            {"start_ms": 1500, "end_ms": 3000, "text": "第二段", "confidence": 0.85},
        ]

        with patch("app.services.transcription.DATA_DIR", tmp_path):
            persist_transcript(memo_id, [], segments, tmp_db)

        conn = get_connection(tmp_db)
        rows = conn.execute(
            "SELECT ordinal, start_ms, end_ms, text, confidence FROM segments WHERE memo_id = ? ORDER BY ordinal",
            (memo_id,),
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == 1  # ordinal
        assert rows[0][3] == "第一段"
        assert rows[1][0] == 2
        assert rows[1][3] == "第二段"

    def test_persist_updates_memo_status(self, tmp_path: Path, tmp_db: Path):
        memo_id = _insert_memo_and_job(tmp_db, str(uuid.uuid4()))
        memo_dir = tmp_path / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)

        with patch("app.services.transcription.DATA_DIR", tmp_path):
            persist_transcript(memo_id, [], [{"start_ms": 0, "end_ms": 100, "text": "t", "confidence": 1.0}], tmp_db)

        conn = get_connection(tmp_db)
        memo = conn.execute(
            "SELECT status, transcript_revision, speaker_count FROM memos WHERE id = ?", (memo_id,)
        ).fetchone()
        conn.close()

        assert memo[0] == "completed"
        assert memo[1] == 1
        assert memo[2] == 0

    def test_persist_replaces_existing_segments(self, tmp_path: Path, tmp_db: Path):
        memo_id = _insert_memo_and_job(tmp_db, str(uuid.uuid4()))
        memo_dir = tmp_path / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)

        with patch("app.services.transcription.DATA_DIR", tmp_path):
            # First persist
            persist_transcript(memo_id, [], [{"start_ms": 0, "end_ms": 100, "text": "old", "confidence": 1.0}], tmp_db)
            # Second persist (retry scenario)
            persist_transcript(memo_id, [], [{"start_ms": 0, "end_ms": 100, "text": "new", "confidence": 0.9}], tmp_db)

        conn = get_connection(tmp_db)
        rows = conn.execute("SELECT text FROM segments WHERE memo_id = ?", (memo_id,)).fetchall()
        conn.close()

        assert len(rows) == 1  # Not duplicated
        assert rows[0][0] == "new"

    def test_persist_multiple_segments(self, tmp_path: Path, tmp_db: Path):
        memo_id = _insert_memo_and_job(tmp_db, str(uuid.uuid4()))
        memo_dir = tmp_path / "memos" / memo_id
        memo_dir.mkdir(parents=True, exist_ok=True)

        segments = [
            {"start_ms": i * 2000, "end_ms": (i + 1) * 2000, "text": f"Segment {i}", "confidence": 0.9}
            for i in range(5)
        ]

        with patch("app.services.transcription.DATA_DIR", tmp_path):
            persist_transcript(memo_id, [], segments, tmp_db)

        conn = get_connection(tmp_db)
        rows = conn.execute(
            "SELECT ordinal, text FROM segments WHERE memo_id = ? ORDER BY ordinal",
            (memo_id,),
        ).fetchall()
        conn.close()

        assert len(rows) == 5
        for i, row in enumerate(rows):
            assert row[0] == i + 1
            assert row[1] == f"Segment {i}"


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    def test_get_models_creates_singleton(self):
        models = get_models()
        assert isinstance(models, TranscriptionModels)
        # Second call returns same instance
        assert get_models() is models

    def test_is_model_ready_false_initially(self):
        assert not is_model_ready()


# ---------------------------------------------------------------------------
# Integration test (requires GPU + models)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests (requires GPU + models)",
)
class TestTranscriptionIntegration:
    """Integration tests that load real FunASR models and run inference.

    Run with: RUN_INTEGRATION_TESTS=1 pytest tests/test_transcription.py -x -k Integration
    """

    def test_full_pipeline_with_real_audio(self, tmp_path: Path, tmp_db: Path):
        """Test the full pipeline with the VAD example WAV file."""
        cache_dir = os.environ.get("MODELSCOPE_CACHE", "/home/appuser/.cache/modelscope")
        example_wav = (
            Path(cache_dir)
            / "models"
            / "iic"
            / "speech_fsmn_vad_zh-cn-16k-common-pytorch"
            / "example"
            / "vad_example.wav"
        )
        if not example_wav.exists():
            pytest.skip("VAD example WAV not found in cache")

        models = get_models()
        result = models.transcribe(example_wav)

        assert result["text"], "Expected non-empty transcript"
        assert len(result["segments"]) > 0, "Expected at least one segment"

        for seg in result["segments"]:
            assert seg["start_ms"] >= 0
            assert seg["end_ms"] > seg["start_ms"]
            assert seg["text"].strip()
            assert 0 <= seg["confidence"] <= 1.0

    def test_vad_with_real_audio(self, tmp_path: Path):
        """Test VAD produces speech segments."""
        cache_dir = os.environ.get("MODELSCOPE_CACHE", "/home/appuser/.cache/modelscope")
        example_wav = (
            Path(cache_dir)
            / "models"
            / "iic"
            / "speech_fsmn_vad_zh-cn-16k-common-pytorch"
            / "example"
            / "vad_example.wav"
        )
        if not example_wav.exists():
            pytest.skip("VAD example WAV not found in cache")

        models = get_models()
        models.load()
        segments = models.run_vad(example_wav)

        assert len(segments) > 0, "Expected speech segments from example audio"
        for start, end in segments:
            assert start >= 0
            assert end > start
