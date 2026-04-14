"""Capability manifest detection — GPU, models, feature support.

VAL-SYS-002: Capability manifest reflects actual runtime state.
"""

from __future__ import annotations

import logging

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
