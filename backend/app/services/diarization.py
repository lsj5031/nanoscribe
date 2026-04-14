"""Diarization service using 3D-Speaker CAM++ model."""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Pastel colors for visual differentiation of speakers
SPEAKER_COLORS = [
    "#00d4ff",
    "#f472b6",
    "#a78bfa",
    "#34d399",
    "#fbbf24",
    "#fb923c",
]


def run_diarization(audio_path: Path) -> list[dict[str, Any]]:
    """Run speaker diarization on an audio file.

    Returns list of {"speaker": "spk0", "start_ms": 0, "end_ms": 5000}.

    Gracefully degrades if 3D-Speaker is not installed.
    Uses GPU on-demand (same pattern as transcription) to avoid VRAM exhaustion.
    """
    try:
        # Ensure 3D-Speaker is importable
        import speakerlab  # noqa: F401
    except ImportError:
        try:
            # Add /opt/3D-Speaker to path if installed via git clone
            sys.path.insert(0, "/opt/3D-Speaker")
            import speakerlab  # noqa: F401
        except ImportError:
            logger.warning(
                "3d_speaker_not_installed",
                hint="git clone https://github.com/modelscope/3D-Speaker /opt/3D-Speaker",
            )
            return []

    try:
        import torch
        import torchaudio

        # Monkey-patch torchaudio for pyannote.audio compatibility:
        # pyannote.audio 3.x calls torchaudio.set_audio_backend() which was
        # removed in torchaudio >= 2.0.  Provide a no-op stub so the import
        # chain doesn't crash.
        if not hasattr(torchaudio, "set_audio_backend"):
            torchaudio.set_audio_backend = lambda _: None  # type: ignore[attr-defined]
        if not hasattr(torchaudio, "get_audio_backend"):
            torchaudio.get_audio_backend = lambda: None  # type: ignore[attr-defined]

        # Monkey-patch torchaudio.load to use soundfile instead of torchcodec.
        # torchcodec requires libnvrtc.so.13 which is unavailable with
        # CUDA 12.x.  soundfile (libsndfile) works reliably for WAV/FLAC/OGG.

        def _soundfile_load(filepath: str | Path, **kwargs):  # type: ignore[no-untyped-def]
            import soundfile

            waveform, sample_rate = soundfile.read(str(filepath), dtype="float32", always_2d=True)
            return torch.from_numpy(waveform.T), sample_rate

        # Only patch if the default backend (torchcodec) is broken
        try:
            torchaudio.load("/dev/null")  # quick probe
        except Exception:
            torchaudio.load = _soundfile_load  # type: ignore[assignment]
            logger.debug("torchaudio_load_patched_soundfile")

        from speakerlab.bin.infer_diarization import Diarization3Dspeaker

        device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

        # Create diarization model directly on the inference device.
        # Like the ASR pipeline, models are ephemeral — created for inference
        # then deleted so VRAM is freed for the next step.
        diarization = Diarization3Dspeaker(device=device)
        try:
            # Diarization3Dspeaker.__call__ returns [[start_s, end_s, speaker_id], ...]
            raw_result = diarization(str(audio_path))
        finally:
            del diarization
            if device.type == "cuda":
                torch.cuda.empty_cache()

        segments: list[dict[str, Any]] = []
        for seg in raw_result:
            start_s, end_s, speaker_id = seg[0], seg[1], seg[2]
            segments.append(
                {
                    "speaker": f"spk{speaker_id}",
                    "start_ms": int(round(start_s * 1000)),
                    "end_ms": int(round(end_s * 1000)),
                }
            )
        return segments
    except Exception:
        logger.exception("diarization_failed")
        return []


def create_speaker_rows(db_path: Path, memo_id: str, segments: list[dict[str, Any]]) -> None:
    """Create memo_speakers rows from diarized segments.

    For each unique speaker_key in the segments, creates a memo_speakers row
    with a default label (Speaker 1, Speaker 2, etc.) and a pastel color.
    Also updates the memo's speaker_count.
    """
    # Find unique speakers in order of first appearance
    seen: set[str] = set()
    speakers: list[str] = []
    for seg in segments:
        spk = seg.get("speaker_key")
        if spk and spk not in seen:
            seen.add(spk)
            speakers.append(spk)

    if not speakers:
        return

    conn = sqlite3.connect(str(db_path))
    try:
        for i, spk in enumerate(speakers):
            color = SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
            display_name = f"Speaker {i + 1}"
            speaker_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO memo_speakers (id, memo_id, speaker_key, display_name, color, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                (speaker_id, memo_id, spk, display_name, color),
            )
        # Update memo speaker_count
        conn.execute(
            "UPDATE memos SET speaker_count = ? WHERE id = ?",
            (len(speakers), memo_id),
        )
        conn.commit()
    finally:
        conn.close()
