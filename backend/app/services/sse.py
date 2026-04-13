"""SSE event manager for real-time job progress streaming.

VAL-TRANS-002: SSE event stream delivers real-time job updates.
VAL-TRANS-003: SSE reconnect delivers current state without replay.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# SSE event types matching SPEC §15.5
EVENT_STAGE = "job.stage"
EVENT_PROGRESS = "job.progress"
EVENT_WAVEFORM_READY = "waveform.ready"
EVENT_COMPLETED = "job.completed"
EVENT_FAILED = "job.failed"
EVENT_CANCELLED = "job.cancelled"

# Throttle interval (VAL-JOB-018: progress updates throttled to ~1/second)
PROGRESS_THROTTLE_SECONDS = 1.0


class SSEEventManager:
    """In-process pub/sub for SSE job events.

    Manages subscriptions keyed by job_id. Each subscriber is an async
    callback that receives event dicts. Used by the SSE endpoint to
    stream events to connected clients.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[dict], Coroutine]]] = {}
        self._last_progress_time: dict[str, float] = {}

    def subscribe(self, job_id: str, callback: Callable[[dict], Coroutine]) -> None:
        """Subscribe to events for a job."""
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(callback)

    def unsubscribe(self, job_id: str, callback: Callable[[dict], Coroutine]) -> None:
        """Unsubscribe a callback from a job's events."""
        if job_id in self._subscribers:
            self._subscribers[job_id] = [cb for cb in self._subscribers[job_id] if cb is not callback]
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]

    def publish(self, job_id: str, event: dict) -> None:
        """Publish an event to all subscribers of a job."""
        callbacks = self._subscribers.get(job_id, [])
        for cb in callbacks:
            try:
                # Fire and forget — the subscriber handles its own event loop
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(cb(event))
                except RuntimeError:
                    # No running loop — create one
                    asyncio.run(cb(event))
            except Exception as exc:
                logger.warning("SSE subscriber error for job %s: %s", job_id, exc)

    def publish_progress(self, job_id: str, progress: float, stage: str | None = None) -> None:
        """Publish a progress event, throttled to ~1/second.

        VAL-JOB-018: No more than one progress event per second.
        """
        now = time.monotonic()
        last = self._last_progress_time.get(job_id, 0)

        if now - last < PROGRESS_THROTTLE_SECONDS and progress < 1.0:
            return  # Throttled

        self._last_progress_time[job_id] = now
        data: dict[str, Any] = {"progress": round(progress, 4)}
        if stage:
            data["stage"] = stage
        self.publish(job_id, {"event": EVENT_PROGRESS, "data": data})

    def publish_stage(self, job_id: str, stage: str) -> None:
        """Publish a stage transition event."""
        self.publish(job_id, {"event": EVENT_STAGE, "data": {"stage": stage}})

    def publish_completed(self, job_id: str) -> None:
        """Publish a job completion event."""
        self.publish(job_id, {"event": EVENT_COMPLETED, "data": {"status": "completed"}})

    def publish_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        """Publish a job failure event."""
        self.publish(
            job_id,
            {
                "event": EVENT_FAILED,
                "data": {"status": "failed", "error_code": error_code, "error_message": error_message},
            },
        )

    def publish_cancelled(self, job_id: str) -> None:
        """Publish a job cancellation event."""
        self.publish(job_id, {"event": EVENT_CANCELLED, "data": {"status": "cancelled"}})


# Module-level singleton
_manager: SSEEventManager | None = None


def get_sse_manager() -> SSEEventManager:
    """Return the singleton SSEEventManager instance."""
    global _manager
    if _manager is None:
        _manager = SSEEventManager()
    return _manager
