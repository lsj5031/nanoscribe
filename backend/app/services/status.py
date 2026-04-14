"""System status service – gathers runtime status info.

Collects GPU info, storage usage, memo count, and cached models.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.services.capabilities import _detect_gpu, _detect_model_ready

logger = logging.getLogger(__name__)

_settings = get_settings()
DATA_DIR = _settings.data_dir


def get_system_status() -> dict:
    """Build the full system status dict.

    Returns a dict matching StatusResponse schema.
    """
    gpu_available, device = _detect_gpu()
    model_loaded = _detect_model_ready()

    # Extract GPU name from device string (e.g. "cuda:NVIDIA RTX 3070")
    gpu_name: str | None = None
    if gpu_available and ":" in device:
        gpu_name = device.split(":", 1)[1]

    # Storage usage
    storage_used_mb = _compute_storage_mb(DATA_DIR)

    # Memo count
    memo_count = _count_memos(DATA_DIR / "nanoscribe.db")

    # Cached models
    models_cached = _get_cached_models()

    status = "ready" if model_loaded else "loading"

    return {
        "status": status,
        "model_loaded": model_loaded,
        "device": device.split(":")[0] if ":" in device else device,
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
        "data_dir": str(DATA_DIR),
        "memo_count": memo_count,
        "storage_used_mb": storage_used_mb,
        "models_cached": models_cached,
    }


def _compute_storage_mb(data_dir: Path) -> float:
    """Sum total file size under data_dir in megabytes."""
    total = 0
    try:
        for f in data_dir.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        logger.debug("Failed to compute storage size", exc_info=True)
    return round(total / (1024 * 1024), 1)


def _count_memos(db_path: Path) -> int:
    """Count memos in the database."""
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            result = conn.execute("SELECT COUNT(*) FROM memos").fetchone()
            return result[0] if result else 0
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to count memos", exc_info=True)
        return 0


def _get_cached_models() -> list[str]:
    """Return list of cached model names."""
    models = []
    try:
        from app.services.transcription import _models

        if _models is not None:
            models.append(_settings.asr_model)
    except Exception:
        pass

    # Always list the expected model names
    expected = [_settings.asr_model, _settings.vad_model, _settings.punc_model]
    # Use a short display name for the ASR model
    display_names = {
        _settings.asr_model: "Fun-ASR-Nano-2512",
        _settings.vad_model: "fsmn-vad",
        _settings.punc_model: "ct-punc",
    }

    result = []
    for m in expected:
        name = display_names.get(m, m)
        if name not in result:
            result.append(name)

    # Check for CAM++ diarization model
    try:
        from pathlib import Path

        hf_cache = Path.home() / ".cache" / "huggingface"
        ms_cache = Path.home() / ".cache" / "modelscope"
        # Check if 3D-Speaker model files exist in either cache
        for cache_dir in [hf_cache, ms_cache]:
            if cache_dir.exists():
                for p in cache_dir.rglob("*"):
                    if "cam++" in p.name.lower() or "3dspeaker" in str(p).lower():
                        if "CAM++" not in result:
                            result.append("CAM++")
                        break
    except Exception:
        pass

    return result
