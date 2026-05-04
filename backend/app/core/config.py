"""Application configuration — single source of truth for env vars.

All environment variable reads must go through the Settings class.
Do not call os.environ.get() or os.getenv() for app config elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    return Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))


def _default_static_dir() -> Path:
    return Path(os.environ.get("NANOSCRIBE_STATIC_DIR", "/app/static"))


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment variables."""

    data_dir: Path = field(default_factory=_default_data_dir)
    static_dir: Path = field(default_factory=_default_static_dir)
    asr_model: str = "FunAudioLLM/Fun-ASR-Nano-2512"
    vad_model: str = "fsmn-vad"
    punc_model: str = "ct-punc"
    host: str = "0.0.0.0"
    port: int = 8000
    offline: bool = field(default_factory=lambda: os.environ.get("NANOSCRIBE_OFFLINE", "0") == "1")
    api_key: str = field(default_factory=lambda: os.environ.get("NANOSCRIBE_API_KEY", ""))
    remote_asr_url: str = field(default_factory=lambda: os.environ.get("NANOSCRIBE_REMOTE_ASR_URL", ""))
    remote_asr_api_key: str = field(default_factory=lambda: os.environ.get("NANOSCRIBE_REMOTE_ASR_API_KEY", ""))
    remote_asr_model: str = field(default_factory=lambda: os.environ.get("NANOSCRIBE_REMOTE_ASR_MODEL", "whisper-1"))
    # ── VAD / chunking parameters for local ASR ───────────────────────
    # 0 = auto-detect based on GPU VRAM
    vad_max_chunk_ms: int = field(default_factory=lambda: int(os.environ.get("NANOSCRIBE_VAD_MAX_CHUNK_MS", "0")))
    vad_merge_gap_ms: int = field(default_factory=lambda: int(os.environ.get("NANOSCRIBE_VAD_MERGE_GAP_MS", "800")))
    vad_chunk_buffer_ms: int = field(
        default_factory=lambda: int(os.environ.get("NANOSCRIBE_VAD_CHUNK_BUFFER_MS", "200"))
    )
    vad_min_chunk_ms: int = field(default_factory=lambda: int(os.environ.get("NANOSCRIBE_VAD_MIN_CHUNK_MS", "400")))
    # "" = auto-detect, "1" = always, "0" = never
    keep_models_warm: str = field(default_factory=lambda: os.environ.get("NANOSCRIBE_KEEP_MODELS_WARM", ""))
    remote_asr_timeout: int = field(default_factory=lambda: int(os.environ.get("NANOSCRIBE_REMOTE_ASR_TIMEOUT", "900")))

    @property
    def db_path(self) -> Path:
        """Database path derived from data_dir."""
        return self.data_dir / "nanoscribe.db"


def get_settings() -> Settings:
    """Return the application settings (singleton-friendly)."""
    return Settings()
