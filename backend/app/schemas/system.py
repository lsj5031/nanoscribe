"""Pydantic models for system endpoints (health, capabilities, status)."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for GET /api/system/health."""

    status: str
    backend: str
    db: str
    storage: str
    model_ready: bool


class CapabilitiesResponse(BaseModel):
    """Response schema for GET /api/system/capabilities.

    VAL-SYS-001: All required keys present with correct types.
    """

    ready: bool
    gpu: bool
    device: str
    asr_model: str
    vad: str
    timestamps: bool
    speaker_diarization: bool
    hotwords: bool
    language_auto_detect: bool
    recording: bool


class ModelReadiness(BaseModel):
    """Readiness info for a single model."""

    name: str
    loaded: bool
    downloading: bool


class ReadinessResponse(BaseModel):
    """Response schema for GET /api/system/readiness."""

    ready: bool
    models: dict[str, ModelReadiness]
    device: str
    gpu_available: bool


class StatusResponse(BaseModel):
    """Response schema for GET /api/system/status."""

    status: str
    model_loaded: bool
    device: str
    gpu_available: bool
    gpu_name: str | None
    data_dir: str
    memo_count: int
    storage_used_mb: float
    models_cached: list[str]
