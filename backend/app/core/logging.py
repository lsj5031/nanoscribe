"""Structured logging configuration — structlog with JSON output and contextvars.

All log records are emitted as single-line JSON objects for easy
machine parsing (jq, Datadog, CloudWatch, etc.).

Usage in application code::

    import structlog
    logger = structlog.get_logger(__name__)

    # Simple message
    logger.info("job_started")

    # With extra structured fields
    logger.info("chunk_processed", chunk_index=3, total_chunks=12, duration_ms=840)

    # Context-bound fields (job_id, memo_id) are automatically included
    # when the worker binds them via contextvars — no need to pass them
    # into every call.

The worker sets context at the top of each job::

    from structlog.contextvars import bind_contextvars, clear_contextvars

    clear_contextvars()
    bind_contextvars(job_id=job_id, memo_id=memo_id)
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def setup_logging(*, json_logs: bool | None = None, level: int = logging.INFO) -> None:
    """Configure structlog + stdlib for unified JSON (or console) output.

    Must be called **once** at application startup, before any
    ``structlog.get_logger()`` calls.

    Parameters
    ----------
    json_logs:
        If *True* (the default), emit one JSON object per log line.
        If *False*, emit human-readable console output (nice for local dev).
    level:
        Python logging level for the root logger (default ``INFO``).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Choose renderer (default: JSON unless LOG_FORMAT=console or no TTY)
    if json_logs is None:
        json_logs = os.environ.get("LOG_FORMAT", "json") != "console"

    if json_logs:
        log_renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        log_renderer = structlog.dev.ConsoleRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            log_renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Route uvicorn loggers through our formatter
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # Suppress noisy libraries
    for name in ("httpx", "httpcore", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)
