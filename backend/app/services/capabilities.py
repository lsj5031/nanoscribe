"""Capability manifest detection — GPU, models, feature support.

VAL-SYS-002: Capability manifest reflects actual runtime state.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


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
        logger.debug("pytorch_not_installed", device="cpu")
        return False, "cpu"
    except RuntimeError as exc:
        logger.warning("gpu_detection_failed", error=str(exc))
        return False, "cpu"


def _detect_model_ready() -> bool:
    """Check whether the core pipeline models are cached on disk.

    Models are loaded ephemerally onto the GPU during inference (not kept
    in memory), so "ready" means the disk cache exists, not that models
    are resident in RAM/VRAM.
    """
    # Check that all core models (ASR, VAD, Punc) are cached on disk
    _OPTIONAL = {"diarization"}
    for key, (org, model_name) in _MODEL_CACHE_INFO.items():
        if key in _OPTIONAL:
            continue
        if not _check_model_cached(org, model_name):
            return False
    return True


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
    "punc": ("iic", "punc_ct-transformer_cn-en-common-vocab471067-large"),
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

    models_info: dict[str, dict] = {}
    all_ready = True

    # Diarization is optional — only core pipeline models (ASR, VAD, Punc)
    # gate the overall readiness flag.
    _OPTIONAL_MODELS = {"diarization"}

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
        downloading = not cached and _model_dir_exists(org, model_name)

        # Only core (non-optional) models gate overall readiness
        if not cached and key not in _OPTIONAL_MODELS:
            all_ready = False

        models_info[key] = {
            "name": display_name,
            "loaded": cached,
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
