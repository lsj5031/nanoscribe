"""Remote transcription adapter — OpenAI-compatible API backend.

When NANOSCRIBE_REMOTE_ASR_URL is configured, this adapter replaces the
local FunASR pipeline.  It sends the normalized audio to a remote endpoint
(OpenAI, Groq, etc.) and converts the OpenAI verbose_json response into
the same ``{raw_output, text, segments}`` format that the local pipeline
produces.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import structlog

from app.services.protocols import TranscriptionError

logger = structlog.get_logger(__name__)


class RemoteTranscriptionService:
    """Transcription via an external OpenAI-compatible /v1/audio/transcriptions API."""

    def __init__(self, url: str, api_key: str, model: str, timeout: int = 900) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    @property
    def device(self) -> str:
        return "remote"

    def transcribe(
        self,
        audio_path: str | Path,
        hotwords: str | None = None,
        chunk_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Call the remote ASR API and return results in local pipeline format."""
        import httpx

        logger.info(
            "remote_transcribe_start",
            audio=str(audio_path),
            url=self.url,
            model=self.model,
        )
        t0 = time.monotonic()

        url = f"{self.url}/audio/transcriptions"
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data: dict[str, str] = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        if hotwords:
            data["prompt"] = hotwords

        try:
            with open(audio_path, "rb") as f:
                files = {"file": ("audio.wav", f, "audio/wav")}

                audio_size = audio_path.stat().st_size if isinstance(audio_path, Path) else 0
                size_based_timeout = max(self.timeout, audio_size // 100_000)
                dynamic_timeout = min(size_based_timeout, 1800)
                logger.info(
                    "remote_transcribe_timeout",
                    base_timeout=self.timeout,
                    audio_size_mb=round(audio_size / 1_000_000, 1),
                    dynamic_timeout_s=dynamic_timeout,
                )
                with httpx.Client(timeout=httpx.Timeout(float(dynamic_timeout), connect=30.0)) as client:
                    resp = client.post(url, data=data, files=files, headers=headers)
        except httpx.TimeoutException as exc:
            raise TranscriptionError(f"Remote ASR request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise TranscriptionError(f"Remote ASR connection failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Remote ASR request failed: {exc}") from exc

        if resp.status_code != 200:
            logger.error(
                "remote_transcribe_failed",
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise TranscriptionError(f"Remote ASR returned HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            res_json = resp.json()
        except Exception as exc:
            raise TranscriptionError(f"Remote ASR returned invalid JSON: {exc}") from exc

        text = res_json.get("text", "").strip()

        segments: list[dict[str, Any]] = []
        for seg in res_json.get("segments", []):
            start_s = seg.get("start", 0.0)
            end_s = seg.get("end", 0.0)
            avg_logprob = seg.get("avg_logprob", 0.0)
            confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
            segments.append(
                {
                    "start_ms": int(round(start_s * 1000)),
                    "end_ms": int(round(end_s * 1000)),
                    "text": seg.get("text", "").strip(),
                    "confidence": round(confidence, 4),
                }
            )

        if not segments and text:
            duration_s = res_json.get("duration", 0.0)
            segments.append(
                {
                    "start_ms": 0,
                    "end_ms": int(round(duration_s * 1000)),
                    "text": text,
                    "confidence": 1.0,
                }
            )

        if chunk_callback is not None:
            try:
                chunk_callback(1, 1)
            except Exception:
                pass

        elapsed = time.monotonic() - t0
        logger.info(
            "remote_transcribe_done",
            segment_count=len(segments),
            text_length=len(text),
            elapsed_s=round(elapsed, 2),
        )

        return {
            "raw_output": [res_json],
            "text": text,
            "segments": segments,
        }
