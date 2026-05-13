"""Transcription backend Protocol — the seam between callers and adapters.

Defines the contract that every transcription backend must satisfy.
Both ``TranscriptionModels`` (local FunASR) and ``RemoteTranscriptionService``
(OpenAI-compatible API) are adapters of this seam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

# Sentence-ending punctuation for segment splitting
_SENTENCE_END = frozenset("。！？.!?;")


class TranscriptionError(Exception):
    """Raised when transcription fails."""


@runtime_checkable
class TranscriptionBackend(Protocol):
    """Interface that every transcription backend must satisfy.

    A backend provides a ``transcribe()`` method that accepts a normalized
    WAV file and returns the standard result dict with keys:
      - raw_output: list[dict] — raw ASR results
      - text: str — combined transcript text
      - segments: list[dict] — segment dicts with start_ms, end_ms, text, confidence
    """

    @property
    def is_loaded(self) -> bool:
        """Whether the backend is loaded and ready for inference."""
        ...

    def load(self) -> None:
        """Load/verify models or connection.

        Called lazily before the first ``transcribe()`` call.
        Must be idempotent (safe to call multiple times).
        """
        ...

    @property
    def device(self) -> str:
        """Target device string (e.g. ``'cuda:0'``, ``'cpu'``, ``'remote'``)."""
        ...

    def transcribe(
        self,
        audio_path: str | Path,
        hotwords: str | None = None,
        chunk_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Run transcription on a normalized WAV file.

        Args:
            audio_path: Path to a 16 kHz mono 16-bit WAV file.
            hotwords: Optional hotword/context string for ASR.
            chunk_callback: Optional callback invoked after each ASR chunk
                with ``(chunks_done, total_chunks)`` for progress reporting.

        Returns:
            Dict with keys: raw_output, text, segments.

        Raises:
            TranscriptionError: on any failure.
        """
        ...
