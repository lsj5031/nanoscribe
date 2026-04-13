"""Audio normalization service — ffmpeg conversion, duration extraction, waveform peaks.

VAL-INTAKE-010: ffmpeg normalizes all supported formats to canonical WAV (16-bit PCM, 16kHz mono).
VAL-INTAKE-011: Duration extracted accurately (within ±100ms).
VAL-INTAKE-012: Waveform peaks extracted and stored as JSON array.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Target format: 16-bit PCM, 16kHz, mono
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes

# Waveform extraction settings
WAVEFORM_PEAKS_PER_SECOND = 100  # ~100 peaks per second of audio
WAVEFORM_MIN_PEAKS = 50


class NormalizationError(Exception):
    """Raised when audio normalization fails."""

    pass


def normalize_audio(source_path: Path, memo_dir: Path) -> Path:
    """Normalize audio file to canonical WAV format using ffmpeg.

    Converts to: 16-bit PCM, 16kHz, mono.
    Stores result as normalized.wav in the memo directory.

    Args:
        source_path: Path to the original audio file.
        memo_dir: Directory to store the normalized output.

    Returns:
        Path to the normalized WAV file.

    Raises:
        NormalizationError: If ffmpeg fails or source file is invalid.
    """
    output_path = memo_dir / "normalized.wav"

    if not source_path.exists():
        raise NormalizationError(f"Source file not found: {source_path}")

    if source_path.stat().st_size == 0:
        raise NormalizationError("Source file is empty (0 bytes). Cannot normalize audio.")

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-i",
        str(source_path),
        "-ac",
        str(TARGET_CHANNELS),  # mono
        "-ar",
        str(TARGET_SAMPLE_RATE),  # 16kHz
        "-sample_fmt",
        "s16",  # 16-bit PCM
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise NormalizationError("ffmpeg normalization timed out after 300 seconds")
    except FileNotFoundError:
        raise NormalizationError("ffmpeg not found — is it installed?")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise NormalizationError(f"Audio normalization failed: {stderr}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise NormalizationError("Audio normalization produced no output")

    logger.info("Normalized audio: %s → %s", source_path.name, output_path.name)
    return output_path


def extract_duration_ms(normalized_path: Path) -> int:
    """Extract audio duration in milliseconds from a normalized WAV file.

    Reads the WAV header directly for fast, accurate duration extraction.

    Args:
        normalized_path: Path to the normalized WAV file.

    Returns:
        Duration in milliseconds (integer).

    Raises:
        NormalizationError: If duration cannot be extracted.
    """
    import wave as wave_mod

    try:
        with wave_mod.open(str(normalized_path), "rb") as wf:
            n_frames = wf.getnframes()
            framerate = wf.getframerate()
            if framerate <= 0:
                raise NormalizationError("Invalid sample rate in normalized WAV")
            duration_seconds = n_frames / framerate
            return int(round(duration_seconds * 1000))
    except NormalizationError:
        raise
    except Exception as exc:
        raise NormalizationError(f"Failed to extract duration: {exc}") from exc


def extract_waveform_peaks(
    normalized_path: Path, memo_dir: Path, peaks_per_second: int = WAVEFORM_PEAKS_PER_SECOND
) -> Path:
    """Extract waveform peak data and store as waveform.json.

    Reads the normalized WAV, downsamples into buckets of peaks_per_second
    per second, and writes the absolute max amplitude per bucket as a JSON
    array of floats in [0, 1].

    Args:
        normalized_path: Path to the normalized WAV file.
        memo_dir: Directory to store waveform.json.
        peaks_per_second: Number of peak values per second of audio.

    Returns:
        Path to the waveform.json file.

    Raises:
        NormalizationError: If waveform extraction fails.
    """
    import wave as wave_mod

    output_path = memo_dir / "waveform.json"

    try:
        with wave_mod.open(str(normalized_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_audio = wf.readframes(n_frames)

        if sample_width != 2:
            raise NormalizationError(f"Expected 16-bit WAV, got {sample_width * 8}-bit")

        # Convert to numpy array (16-bit signed PCM)
        audio = np.frombuffer(raw_audio, dtype=np.int16)

        # If stereo, take first channel
        if n_channels > 1:
            audio = audio[::n_channels]

        # Calculate bucket size
        total_samples = len(audio)
        duration_seconds = total_samples / framerate
        n_buckets = max(WAVEFORM_MIN_PEAKS, int(duration_seconds * peaks_per_second))

        # Reshape into buckets and compute max absolute amplitude per bucket
        bucket_size = total_samples / n_buckets
        peaks = []
        for i in range(n_buckets):
            start = int(i * bucket_size)
            end = int((i + 1) * bucket_size)
            end = min(end, total_samples)
            if start >= end:
                continue
            chunk = audio[start:end]
            # Normalize to [0, 1] range (32767 is max for int16)
            peak = float(np.max(np.abs(chunk))) / 32767.0
            peaks.append(round(peak, 4))

        # Write JSON
        output_path.write_text(json.dumps(peaks))

        logger.info("Extracted %d waveform peaks from %s", len(peaks), normalized_path.name)
        return output_path

    except NormalizationError:
        raise
    except Exception as exc:
        raise NormalizationError(f"Failed to extract waveform: {exc}") from exc
