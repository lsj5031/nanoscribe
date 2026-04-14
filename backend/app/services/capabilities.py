"""Capability manifest detection — GPU, models, feature support.

VAL-SYS-002: Capability manifest reflects actual runtime state.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _detect_gpu() -> tuple[bool, str]:
    """Detect GPU availability and return (has_gpu, device_description).

    Returns:
        Tuple of (gpu_available, device_string).
        device_string is e.g. "cuda:NVIDIA RTX 3070" or "cpu".
    """
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return True, f"cuda:{name}"
        return False, "cpu"
    except ImportError:
        logger.debug("PyTorch not installed, defaulting to CPU")
        return False, "cpu"
    except Exception as exc:
        logger.warning("GPU detection failed: %s", exc)
        return False, "cpu"


def _detect_model_ready() -> bool:
    """Check whether the ASR model is loaded and the pipeline can accept jobs."""
    from app.services.transcription import is_model_ready

    return is_model_ready()


def get_capabilities() -> dict:
    """Build the full capability manifest reflecting runtime state.

    Returns a dict matching CapabilitiesResponse schema.
    """
    gpu, device = _detect_gpu()

    return {
        "ready": _detect_model_ready(),
        "gpu": gpu,
        "device": device,
        "asr_model": "FunAudioLLM/Fun-ASR-Nano-2512",
        "vad": "fsmn-vad",
        "timestamps": True,
        "speaker_diarization": True,
        "hotwords": True,
        "language_auto_detect": True,
        "recording": True,
    }


# Model identifiers mapped to their ModelScope cache paths.
# ModelScope stores models under <cache_dir>/models/<org>/<model_name>/
_MODEL_CACHE_INFO: dict[str, tuple[str, str]] = {
    "asr": ("FunAudioLLM", "Fun-ASR-Nano-2512"),
    "vad": ("iic", "speech_fsmn_vad_zh-cn-16k-common-pytorch"),
    "punc": ("iic", "punc_ct-transformer_zh-cn-common-vocab272727-pytorch"),
    "diarization": ("iic", "3dspeaker_speech_campplus_sv_zh-cn_16k-common"),
}


def _get_modelscope_cache_dir() -> Path:
    """Return the ModelScope cache root directory."""
    env = os.environ.get("MODELSCOPE_CACHE")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "modelscope"


def _check_model_cached(org: str, model_name: str) -> bool:
    """Check whether a model's cache directory exists with content.

    A model is considered cached if its directory exists and contains at
    least one file (not just an empty directory created by a failed download).
    """
    cache_root = _get_modelscope_cache_dir()
    model_dir = cache_root / "models" / org / model_name
    if not model_dir.is_dir():
        return False
    # Check that there's at least one real file (not just empty dirs)
    return any(f.is_file() for f in model_dir.rglob("*"))


def get_readiness() -> dict:
    """Build the readiness manifest with per-model cache status.

    Returns a dict matching ReadinessResponse schema.  For each model:
      - loaded=True  if the model is loaded in memory (via TranscriptionModels)
      - downloading=True if we detect a partial download (has directory but no files)
      - Both false if the model directory doesn't exist at all
    """
    gpu, device = _detect_gpu()

    # Check in-memory loading first
    from app.services.transcription import is_model_ready

    models_loaded = is_model_ready()

    models_info: dict[str, dict] = {}
    all_ready = True

    for key, (org, model_name) in _MODEL_CACHE_INFO.items():
        display_name = model_name
        # Use friendlier display names
        if key == "asr":
            display_name = "Fun-ASR-Nano-2512"
        elif key == "vad":
            display_name = "fsmn-vad"
        elif key == "punc":
            display_name = "ct-punc"
        elif key == "diarization":
            display_name = "CAM++"

        cached = _check_model_cached(org, model_name)

        # If models are loaded in memory, all cached models are ready
        loaded = models_loaded and cached
        downloading = not cached and _model_dir_exists(org, model_name)

        if not loaded:
            all_ready = False

        models_info[key] = {
            "name": display_name,
            "loaded": loaded,
            "downloading": downloading,
        }

    # Determine device string (short form)
    device_short = device.split(":")[0] if ":" in device else device

    return {
        "ready": all_ready,
        "models": models_info,
        "device": device_short,
        "gpu_available": gpu,
    }


def _model_dir_exists(org: str, model_name: str) -> bool:
    """Check if a model directory exists at all (even if empty/partial)."""
    cache_root = _get_modelscope_cache_dir()
    model_dir = cache_root / "models" / org / model_name
    return model_dir.is_dir()
