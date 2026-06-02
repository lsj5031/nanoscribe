"""Engine configuration and model lifecycle management.

Owns:
  - ``get_active_engine_config()`` — merges env var defaults with DB overrides
  - ``get_models()`` — singleton factory that returns a ``TranscriptionBackend``
  - ``reset_models()`` — clears the singleton for hot-reload
  - ``is_model_ready()`` — readiness check
"""

from __future__ import annotations

import structlog

from app.core.config import get_settings
from app.services.protocols import TranscriptionBackend

logger = structlog.get_logger(__name__)

_settings = get_settings()


def get_active_engine_config() -> dict[str, str]:
    """Merge environment-variable defaults with database overrides.

    Returns a dict with keys: engine, remote_url, remote_api_key, remote_model.
    The ``engine`` value is "remote" if a remote URL is configured (via
    env var or DB override), otherwise "local".
    """
    config: dict[str, str] = {
        "engine": "remote" if _settings.remote_asr_url else "local",
        "remote_url": _settings.remote_asr_url,
        "remote_api_key": _settings.remote_asr_api_key,
        "remote_model": _settings.remote_asr_model,
        "remote_timeout": str(_settings.remote_asr_timeout),
    }

    db_path = _settings.db_path
    if not db_path.exists():
        return config

    try:
        from app.db import db_connection

        with db_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT key, value FROM system_settings "
                "WHERE key IN ('engine', 'remote_url', 'remote_api_key', 'remote_model', 'remote_timeout')"
            ).fetchall()
            for k, v in rows:
                config[k] = v
    except Exception as exc:
        logger.warning("failed_to_read_settings_db", error=str(exc))

    return config


# Module-level singleton for the active transcription backend
_models: TranscriptionBackend | None = None


def get_models() -> TranscriptionBackend:
    """Return the singleton transcription backend instance.

    Reads the active engine config (env vars + DB overrides) to decide
    whether to use local FunASR or a remote OpenAI-compatible API.
    The return type is ``TranscriptionBackend`` Protocol (structural typing).
    """
    global _models
    if _models is None:
        config = get_active_engine_config()
        if config["engine"] == "remote" and config["remote_url"]:
            url = config["remote_url"]
            if not url.rstrip("/").endswith("/v1"):
                logger.warning(
                    "remote_asr_url_missing_v1",
                    hint="NANOSCRIBE_REMOTE_ASR_URL should include /v1 prefix (e.g. https://api.openai.com/v1)",
                    url=url,
                )
            logger.info(
                "using_remote_asr",
                url=url,
                model=config["remote_model"],
            )
            from app.services.remote_transcription import RemoteTranscriptionService

            _models = RemoteTranscriptionService(
                url=url,
                api_key=config["remote_api_key"],
                model=config["remote_model"],
                timeout=int(config.get("remote_timeout", _settings.remote_asr_timeout)),
            )
        else:
            logger.info("using_local_asr")
            from app.services.local_transcription import TranscriptionModels

            _models = TranscriptionModels()
    return _models


def reset_models() -> None:
    """Clear the active model singleton so the next call re-evaluates config.

    Called after engine settings are changed via the API so that the
    next transcription job picks up the new engine without restart.
    Also unloads any warm-cached models from GPU memory.
    """
    global _models
    if _models is not None:
        try:
            from app.services.local_transcription import TranscriptionModels

            if isinstance(_models, TranscriptionModels):
                _models.unload_models()
        except ImportError:
            pass
    _models = None
    logger.info("transcription_models_reset")


def is_model_ready() -> bool:
    """Check if the ASR model is loaded and ready.

    Always returns True for remote ASR (no local models to verify).
    """
    if _models is None:
        config = get_active_engine_config()
        if config["engine"] == "remote" and config["remote_url"]:
            return True
        return False
    # Duck-type check for is_loaded
    loaded = getattr(_models, "is_loaded", False)
    return bool(loaded)


def models_initialized() -> bool:
    """Return True if the models singleton has been created."""
    return _models is not None
