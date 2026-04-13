"""Tests for audio normalization service.

Covers assertions:
  VAL-INTAKE-010: ffmpeg normalizes audio to canonical WAV
  VAL-INTAKE-011: Duration extracted accurately (within ±100ms)
  VAL-INTAKE-012: Waveform peaks extracted and stored as JSON
"""

from __future__ import annotations

import io
import json
import os
import struct
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("NANOSCRIBE_DATA_DIR", "/tmp/nanoscribe-test-data")
os.environ.setdefault("NANOSCRIBE_STATIC_DIR", "/tmp/nanoscribe-test-static")

from app.services.normalization import (
    NormalizationError,
    extract_duration_ms,
    extract_waveform_peaks,
    normalize_audio,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wav(
    duration_ms: int = 500,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
    frequency: float = 440.0,
) -> bytes:
    """Generate a valid WAV file with a sine wave tone."""
    buf = io.BytesIO()
    n_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        # Generate sine wave samples
        samples = []
        for i in range(n_samples):
            t = i / sample_rate
            val = int(32767 * 0.5 * np.sin(2 * np.pi * frequency * t))
            samples.append(struct.pack("<h", val))
        wf.writeframes(b"".join(samples))
    return buf.getvalue()


def _make_silent_wav(duration_ms: int = 100, sample_rate: int = 16000) -> bytes:
    """Generate a valid WAV file with silence."""
    buf = io.BytesIO()
    n_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


def _make_stereo_wav(duration_ms: int = 200, sample_rate: int = 44100) -> bytes:
    """Generate a valid stereo WAV file at 44.1kHz."""
    buf = io.BytesIO()
    n_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = b"\x00\x00\x00\x00" * n_samples
        wf.writeframes(frames)
    return buf.getvalue()


def _make_corrupt_wav() -> bytes:
    """Generate a .wav file with random garbage content."""
    return os.urandom(1024)


def _make_zero_byte_file() -> bytes:
    """Return zero bytes."""
    return b""


def _create_mp3_via_ffmpeg(wav_content: bytes, tmp_path: Path, name: str = "test.mp3") -> Path:
    """Convert WAV bytes to MP3 using ffmpeg. Returns the MP3 file path."""
    wav_path = tmp_path / "input.wav"
    mp3_path = tmp_path / name
    wav_path.write_bytes(wav_content)
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "9", str(mp3_path)],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"ffmpeg not available or failed: {result.stderr.decode()}")
    return mp3_path


def _create_ogg_via_ffmpeg(wav_content: bytes, tmp_path: Path, name: str = "test.ogg") -> Path:
    """Convert WAV bytes to OGG using ffmpeg. Returns the OGG file path."""
    wav_path = tmp_path / "input.wav"
    ogg_path = tmp_path / name
    wav_path.write_bytes(wav_content)
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libvorbis", "-q:a", "1", str(ogg_path)],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"ffmpeg not available or failed: {result.stderr.decode()}")
    return ogg_path


def _ffprobe_duration(path: str | Path) -> float:
    """Get duration in seconds from ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-i",
            str(path),
            "-show_entries",
            "format=duration",
            "-v",
            "quiet",
            "-of",
            "csv=p=0",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memo_dir(tmp_path: Path) -> Path:
    """Create and return a memo directory for testing."""
    d = tmp_path / "memos" / "test-memo-id"
    d.mkdir(parents=True)
    return d


# ---------------------------------------------------------------------------
# Tests: normalize_audio
# ---------------------------------------------------------------------------


class TestNormalizeAudio:
    """VAL-INTAKE-010: ffmpeg normalizes audio to canonical WAV."""

    def test_wav_input_produces_normalized_wav(self, memo_dir: Path) -> None:
        """A valid WAV input should produce normalized.wav with canonical format."""
        wav_content = _make_wav(duration_ms=500, sample_rate=44100, channels=2)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)

        output = memo_dir / "normalized.wav"
        assert output.exists(), "normalized.wav should be created"
        assert output.stat().st_size > 0, "normalized.wav should not be empty"

    def test_normalized_wav_is_16bit_pcm_16khz_mono(self, memo_dir: Path) -> None:
        """Normalized WAV must be: PCM 16-bit, 16kHz, mono."""
        # Use stereo 44.1kHz input to verify conversion
        wav_content = _make_stereo_wav(duration_ms=200, sample_rate=44100)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)

        output = memo_dir / "normalized.wav"
        with wave.open(str(output), "rb") as wf:
            assert wf.getnchannels() == 1, "Should be mono"
            assert wf.getsampwidth() == 2, "Should be 16-bit (2 bytes per sample)"
            assert wf.getframerate() == 16000, "Should be 16kHz"

    def test_mp3_input_normalizes(self, memo_dir: Path, tmp_path: Path) -> None:
        """MP3 input should normalize to canonical WAV."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000)
        mp3_path = _create_mp3_via_ffmpeg(wav_content, tmp_path)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(mp3_path.read_bytes())

        normalize_audio(source_path, memo_dir)

        output = memo_dir / "normalized.wav"
        assert output.exists()
        with wave.open(str(output), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000

    def test_ogg_input_normalizes(self, memo_dir: Path, tmp_path: Path) -> None:
        """OGG input should normalize to canonical WAV."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000)
        ogg_path = _create_ogg_via_ffmpeg(wav_content, tmp_path)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(ogg_path.read_bytes())

        normalize_audio(source_path, memo_dir)

        output = memo_dir / "normalized.wav"
        assert output.exists()
        with wave.open(str(output), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000

    def test_corrupt_input_raises_error(self, memo_dir: Path) -> None:
        """Corrupt file should raise NormalizationError with clear message."""
        source_path = memo_dir / "source.original"
        source_path.write_bytes(_make_corrupt_wav())

        with pytest.raises(NormalizationError) as exc_info:
            normalize_audio(source_path, memo_dir)

        assert "normalization" in str(exc_info.value).lower() or "ffmpeg" in str(exc_info.value).lower()

    def test_zero_byte_input_raises_error(self, memo_dir: Path) -> None:
        """Zero-byte file should raise NormalizationError."""
        source_path = memo_dir / "source.original"
        source_path.write_bytes(_make_zero_byte_file())

        with pytest.raises(NormalizationError):
            normalize_audio(source_path, memo_dir)

    def test_nonexistent_source_raises_error(self, memo_dir: Path) -> None:
        """Nonexistent source file should raise NormalizationError."""
        source_path = memo_dir / "source.original"
        # File doesn't exist

        with pytest.raises(NormalizationError):
            normalize_audio(source_path, memo_dir)

    def test_output_overwrites_existing(self, memo_dir: Path) -> None:
        """If normalized.wav already exists, it should be overwritten."""
        wav_content = _make_wav(duration_ms=200)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        # Create a pre-existing normalized.wav with wrong content
        (memo_dir / "normalized.wav").write_bytes(b"garbage")

        normalize_audio(source_path, memo_dir)

        output = memo_dir / "normalized.wav"
        assert output.exists()
        # Verify it's actually a valid WAV now
        with wave.open(str(output), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000


# ---------------------------------------------------------------------------
# Tests: extract_duration_ms
# ---------------------------------------------------------------------------


class TestExtractDurationMs:
    """VAL-INTAKE-011: Duration extracted accurately (within ±100ms)."""

    def test_duration_from_normalized_wav(self, memo_dir: Path) -> None:
        """Duration should match the actual audio length within ±100ms."""
        target_ms = 1000
        wav_content = _make_wav(duration_ms=target_ms, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"

        duration = extract_duration_ms(normalized_path)

        assert duration > 0, "Duration must be positive"
        # Allow ±100ms tolerance (ffmpeg may add/remove a few samples)
        assert abs(duration - target_ms) <= 100, f"Duration {duration}ms not within ±100ms of {target_ms}ms"

    def test_duration_30_seconds(self, memo_dir: Path) -> None:
        """Longer audio file duration should be accurate."""
        target_ms = 5000
        wav_content = _make_wav(duration_ms=target_ms, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"

        duration = extract_duration_ms(normalized_path)

        assert abs(duration - target_ms) <= 100, f"Duration {duration}ms not within ±100ms of {target_ms}ms"

    def test_duration_matches_ffprobe(self, memo_dir: Path) -> None:
        """Duration should match ffprobe's reported duration within ±100ms."""
        wav_content = _make_wav(duration_ms=2000, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"

        our_duration = extract_duration_ms(normalized_path)
        ffprobe_duration = _ffprobe_duration(normalized_path) * 1000

        assert abs(our_duration - ffprobe_duration) <= 100, (
            f"Our {our_duration}ms vs ffprobe {ffprobe_duration}ms — not within ±100ms"
        )

    def test_duration_from_stereo_44khz_source(self, memo_dir: Path) -> None:
        """Duration should be accurate even when source was stereo 44.1kHz."""
        target_ms = 1500
        wav_content = _make_stereo_wav(duration_ms=target_ms, sample_rate=44100)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"

        duration = extract_duration_ms(normalized_path)
        assert abs(duration - target_ms) <= 100

    def test_duration_short_audio(self, memo_dir: Path) -> None:
        """Very short audio (100ms) should still have reasonable duration."""
        wav_content = _make_wav(duration_ms=100, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"

        duration = extract_duration_ms(normalized_path)
        assert duration > 0
        assert duration >= 50, "Short audio should still report some duration"


# ---------------------------------------------------------------------------
# Tests: extract_waveform_peaks
# ---------------------------------------------------------------------------


class TestExtractWaveformPeaks:
    """VAL-INTAKE-012: Waveform peaks extracted and stored as JSON."""

    def test_waveform_json_created(self, memo_dir: Path) -> None:
        """waveform.json should be created in memo directory."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        waveform_path = memo_dir / "waveform.json"
        assert waveform_path.exists(), "waveform.json should be created"

    def test_waveform_json_is_valid_json(self, memo_dir: Path) -> None:
        """waveform.json should contain valid JSON."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        waveform_path = memo_dir / "waveform.json"
        data = json.loads(waveform_path.read_text())
        assert isinstance(data, list), "Waveform should be a JSON array"

    def test_waveform_peaks_are_numeric(self, memo_dir: Path) -> None:
        """Waveform peaks should be numeric values."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        data = json.loads((memo_dir / "waveform.json").read_text())
        assert len(data) > 0, "Should have at least some peaks"
        for peak in data:
            assert isinstance(peak, (int, float)), f"Peak should be numeric, got {type(peak)}"

    def test_waveform_peaks_proportional_to_duration(self, memo_dir: Path) -> None:
        """Waveform array length should be proportional to audio duration."""
        wav_content = _make_wav(duration_ms=2000, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        data = json.loads((memo_dir / "waveform.json").read_text())
        # We expect roughly 100-2000 peaks for a 2s audio
        assert 50 <= len(data) <= 5000, f"Peak count {len(data)} unexpected for 2s audio"

    def test_waveform_peaks_in_valid_range(self, memo_dir: Path) -> None:
        """Peak values should be in [0, 1] range (normalized amplitudes)."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000, frequency=440.0)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        data = json.loads((memo_dir / "waveform.json").read_text())
        for peak in data:
            assert 0.0 <= peak <= 1.0, f"Peak {peak} outside [0, 1] range"

    def test_waveform_nonzero_for_tone(self, memo_dir: Path) -> None:
        """Waveform peaks for a tone should have non-zero values."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000, frequency=440.0)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        data = json.loads((memo_dir / "waveform.json").read_text())
        max_peak = max(data)
        assert max_peak > 0.0, "Tone audio should have non-zero peaks"

    def test_waveform_silent_audio_peaks_near_zero(self, memo_dir: Path) -> None:
        """Silent audio should have waveform peaks near zero."""
        wav_content = _make_silent_wav(duration_ms=500, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        data = json.loads((memo_dir / "waveform.json").read_text())
        max_peak = max(data)
        assert max_peak < 0.01, f"Silent audio peaks should be near zero, got {max_peak}"

    def test_waveform_from_mp3_source(self, memo_dir: Path, tmp_path: Path) -> None:
        """Waveform should work for audio normalized from MP3."""
        wav_content = _make_wav(duration_ms=1000, sample_rate=16000)
        mp3_path = _create_mp3_via_ffmpeg(wav_content, tmp_path)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(mp3_path.read_bytes())

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        waveform_path = memo_dir / "waveform.json"
        assert waveform_path.exists()
        data = json.loads(waveform_path.read_text())
        assert len(data) > 0

    def test_waveform_overwrites_existing(self, memo_dir: Path) -> None:
        """If waveform.json already exists, it should be overwritten."""
        wav_content = _make_wav(duration_ms=500, sample_rate=16000)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        # Create a pre-existing waveform.json
        (memo_dir / "waveform.json").write_text("[1,2,3]")

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        extract_waveform_peaks(normalized_path, memo_dir)

        data = json.loads((memo_dir / "waveform.json").read_text())
        assert data != [1, 2, 3], "Should have been overwritten with actual peaks"


# ---------------------------------------------------------------------------
# Tests: Integration - full normalization pipeline
# ---------------------------------------------------------------------------


class TestNormalizationIntegration:
    """Integration tests for the full normalization pipeline."""

    def test_full_pipeline_wav(self, memo_dir: Path) -> None:
        """Full pipeline: normalize → duration → waveform for WAV input."""
        wav_content = _make_wav(duration_ms=1000, sample_rate=44100)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(wav_content)

        # Normalize
        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"
        assert normalized_path.exists()

        # Duration (ffmpeg resamples 44100→16000, may slightly alter length)
        duration = extract_duration_ms(normalized_path)
        assert abs(duration - 1000) <= 150

        # Waveform
        extract_waveform_peaks(normalized_path, memo_dir)
        waveform_path = memo_dir / "waveform.json"
        assert waveform_path.exists()
        data = json.loads(waveform_path.read_text())
        assert isinstance(data, list) and len(data) > 0

    def test_full_pipeline_mp3(self, memo_dir: Path, tmp_path: Path) -> None:
        """Full pipeline for MP3 input."""
        wav_content = _make_wav(duration_ms=2000, sample_rate=16000)
        mp3_path = _create_mp3_via_ffmpeg(wav_content, tmp_path)
        source_path = memo_dir / "source.original"
        source_path.write_bytes(mp3_path.read_bytes())

        normalize_audio(source_path, memo_dir)
        normalized_path = memo_dir / "normalized.wav"

        duration = extract_duration_ms(normalized_path)
        assert abs(duration - 2000) <= 100

        extract_waveform_peaks(normalized_path, memo_dir)
        data = json.loads((memo_dir / "waveform.json").read_text())
        assert len(data) > 0

    def test_preprocessing_failure_clear_error(self, memo_dir: Path) -> None:
        """VAL-INTAKE-007: Corrupt input → job fails with clear error message."""
        source_path = memo_dir / "source.original"
        source_path.write_bytes(b"\x00" * 100)  # minimal corrupt content

        with pytest.raises(NormalizationError) as exc_info:
            normalize_audio(source_path, memo_dir)

        error_msg = str(exc_info.value)
        assert len(error_msg) > 0, "Error message should not be empty"
