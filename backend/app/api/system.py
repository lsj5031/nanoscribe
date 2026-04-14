"""System API endpoints – health, capabilities, status."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.db import check_db_health
from app.schemas.system import CapabilitiesResponse, HealthResponse, ReadinessResponse, StatusResponse
from app.services.capabilities import get_capabilities, get_readiness
from app.services.status import get_system_status

router = APIRouter(tags=["system"])

_settings = get_settings()
DATA_DIR = _settings.data_dir


def _check_storage() -> str:
    """Check if the data directory is writable."""
    try:
        test_file = DATA_DIR / ".healthcheck_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return "ok"
    except OSError:
        return "error"


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return component-level health status.

    VAL-SYS-003: Always returns HTTP 200 — health checks are informational, not errors.
    VAL-SYS-004: Individual components report their own status; partial degradation
    never causes a 5xx response.
    """
    db_status = check_db_health(DATA_DIR / "nanoscribe.db")
    storage_status = _check_storage()
    model_ready = get_capabilities()["ready"]

    all_ok = db_status == "ok" and storage_status == "ok" and model_ready

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        backend="ok",
        db=db_status,
        storage=storage_status,
        model_ready=model_ready,
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    """Return the runtime capability manifest.

    VAL-SYS-001: Returns all required fields with correct types.
    VAL-SYS-002: Reflects actual runtime state (GPU, device, model readiness).
    """
    caps = get_capabilities()
    return CapabilitiesResponse(**caps)


@router.get("/status", response_model=StatusResponse)
async def system_status() -> StatusResponse:
    """Return runtime system status.

    Provides GPU info, storage usage, memo count, and cached models.
    """
    status = get_system_status()
    return StatusResponse(**status)


@router.get("/readiness", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """Return model readiness status with per-model cache state.

    Checks whether each required model (ASR, VAD, Punc, Diarization)
    is cached locally. Used by the frontend to show a first-run
    readiness card when models are not yet available.
    """
    data = get_readiness()
    return ReadinessResponse(**data)
