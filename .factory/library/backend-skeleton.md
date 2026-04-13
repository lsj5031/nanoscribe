# Backend Skeleton & System Endpoints

## What was implemented

FastAPI backend skeleton under `backend/app/` with system endpoints for health and capability manifest.

## Directory Structure

```
backend/app/
  __init__.py
  main.py              # App factory, SPA serving, /api route registration
  api/
    __init__.py
    system.py          # GET /api/system/health, GET /api/system/capabilities
  core/
    __init__.py
    config.py          # Settings dataclass (data_dir, static_dir, db_path, model names)
    dependencies.py    # FastAPI dependency helpers (settings_dep, get_db_connection)
  db/
    __init__.py        # SQLite connection management (WAL mode, FK enforcement, health check)
  schemas/
    __init__.py
    system.py          # Pydantic models: HealthResponse, CapabilitiesResponse
  services/
    __init__.py
    capabilities.py    # Runtime detection: GPU (torch.cuda), model readiness, feature flags
```

## System Endpoints

### GET /api/system/health
Returns component-level health: `status`, `backend`, `db`, `storage`, `model_ready`.
Uses `check_db_health()` and `get_capabilities()` from services.
Status is "ok" or "degraded" — always returns HTTP 200.

### GET /api/system/capabilities
Returns full capability manifest with all required fields:
- `ready` (bool) - whether ASR pipeline can accept jobs
- `gpu` (bool) - GPU detected via `torch.cuda.is_available()`
- `device` (str) - e.g. "cuda:NVIDIA GeForce RTX 3070" or "cpu"
- `asr_model` (str) - "FunAudioLLM/Fun-ASR-Nano-2512"
- `vad` (str) - "fsmn-vad"
- `timestamps` (bool) - always true (FunASR supports timestamps)
- `speaker_diarization` (bool) - false until M6
- `hotwords` (bool) - true
- `language_auto_detect` (bool) - true
- `recording` (bool) - true

## Key Decisions

- `Settings` is a frozen dataclass with computed `db_path` property (avoids ty type errors)
- GPU detection is in `services/capabilities.py` using a lazy approach — reads torch at call time
- DB health check extracted to `db/__init__.py` for reuse across endpoints
- Pydantic response models ensure typed API contracts
- `model_ready` is currently hardcoded to `False`; will be updated in M3 when FunASR model loading is implemented

## Validation Assertions Fulfilled

- VAL-SYS-001: Capability manifest returns all required fields with correct types
- VAL-SYS-002: Capability manifest reflects actual runtime state (GPU detection)
