"""System API endpoints – health, capabilities, status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.db import check_db_health, db_connection
from app.schemas.system import (
    CapabilitiesResponse,
    EngineSettingsResponse,
    EngineSettingsUpdate,
    HealthResponse,
    ReadinessResponse,
    StatusResponse,
)
from app.services.capabilities import get_capabilities, get_readiness
from app.services.status import get_system_status
from app.services.transcription import get_active_engine_config, reset_models

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


@router.get("/settings/engine", response_model=EngineSettingsResponse)
async def get_engine_settings() -> EngineSettingsResponse:
    """Return the current transcription engine configuration.

    Merges environment-variable defaults with database overrides.
    The API key is masked in the response for security.
    """
    config = get_active_engine_config()
    # Mask the API key for display
    if config["remote_api_key"]:
        config["remote_api_key"] = "********"
    # Convert string values from DB to proper types
    config["remote_timeout"] = int(config.get("remote_timeout", 900))
    return EngineSettingsResponse(**config)


@router.put("/settings/engine", response_model=EngineSettingsResponse)
async def update_engine_settings(data: EngineSettingsUpdate) -> EngineSettingsResponse:
    """Update the transcription engine configuration.

    Persists overrides to the database and hot-reloads the engine
    singleton so the next transcription job uses the new config.

    Send ``remote_api_key: null`` or the masked string ``"********"``
    to keep the existing key unchanged.
    """
    # Validate: remote engine requires a URL
    if data.engine == "remote" and not data.remote_url:
        raise HTTPException(
            status_code=422,
            detail="Remote engine requires an endpoint URL.",
        )

    curr = get_active_engine_config()

    # Preserve existing API key if the client sent the masked placeholder
    new_api_key = data.remote_api_key
    if new_api_key is None or new_api_key == "********":
        new_api_key = curr.get("remote_api_key", "")

    # Preserve remote settings when switching to local so the user
    # can switch back without re-entering them.
    remote_url = data.remote_url if data.remote_url else curr.get("remote_url", "")
    remote_model = data.remote_model if data.remote_model else curr.get("remote_model", "whisper-1")
    remote_timeout = str(data.remote_timeout) if data.remote_timeout is not None else curr.get("remote_timeout", "900")

    # Persist all keys to the database
    updates = [
        ("engine", data.engine),
        ("remote_url", remote_url),
        ("remote_api_key", new_api_key),
        ("remote_model", remote_model),
        ("remote_timeout", remote_timeout),
    ]

    db_path = _settings.db_path
    with db_connection(db_path) as conn:
        for k, v in updates:
            conn.execute(
                """INSERT INTO system_settings (key, value)
                   VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (k, v),
            )
        conn.commit()

    # Hot-reload: reset the singleton so next get_models() re-evaluates
    reset_models()

    # Return the updated config (with masked key)
    updated = get_active_engine_config()
    if updated["remote_api_key"]:
        updated["remote_api_key"] = "********"
    updated["remote_timeout"] = int(updated.get("remote_timeout", 900))
    return EngineSettingsResponse(**updated)
