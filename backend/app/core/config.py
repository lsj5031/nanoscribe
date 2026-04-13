"""Application configuration loaded from environment variables."""

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
    """Immutable application settings."""

    data_dir: Path = field(default_factory=_default_data_dir)
    static_dir: Path = field(default_factory=_default_static_dir)
    asr_model: str = "FunAudioLLM/Fun-ASR-Nano-2512"
    vad_model: str = "fsmn-vad"
    punc_model: str = "ct-punc"
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def db_path(self) -> Path:
        """Database path derived from data_dir."""
        return self.data_dir / "nanoscribe.db"


def get_settings() -> Settings:
    """Return the application settings (singleton-friendly)."""
    return Settings()
