"""System API endpoints – health, capabilities."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from app.db import check_db_health
from app.schemas.system import CapabilitiesResponse, HealthResponse
from app.services.capabilities import get_capabilities

router = APIRouter(tags=["system"])

DATA_DIR = Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))


def _check_storage() -> str:
    """Check if the data directory is writable."""
    try:
        test_file = DATA_DIR / ".healthcheck_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return "ok"
    except Exception:
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
