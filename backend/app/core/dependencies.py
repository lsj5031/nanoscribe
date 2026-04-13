"""FastAPI dependency injection helpers."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    return get_settings()


def settings_dep() -> Settings:
    """FastAPI dependency that provides application settings."""
    return _cached_settings()
