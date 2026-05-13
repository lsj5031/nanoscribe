"""Backward-compatible re-exports for the split transcription modules.

This module re-exports everything that was originally defined here
so that existing import patterns continue to work.  New code should
import directly from the focused modules:

  - ``app.services.protocols`` — ``TranscriptionBackend``, ``TranscriptionError``, ``_SENTENCE_END``
  - ``app.services.engine_config`` — ``get_models``, ``reset_models``, ``is_model_ready``, ``get_active_engine_config``
  - ``app.services.local_transcription`` — ``TranscriptionModels``, ``_get_remote_code_path``
  - ``app.services.remote_transcription`` — ``RemoteTranscriptionService``
  - ``app.services.segments_builder`` — ``merge_vad_segments``, ``extract_chunk``,
    ``build_segments_from_timestamps``, etc.
  - ``app.services.persist`` — ``persist_transcript``

See the individual module docstrings for details.
"""

from app.services.engine_config import (
    _models,
    get_active_engine_config,
    get_models,
    is_model_ready,
    models_initialized,
    reset_models,
)
from app.services.local_transcription import (
    TranscriptionModels,
    _get_remote_code_path,
)
from app.services.persist import (
    _now_iso,
    persist_transcript,
)
from app.services.protocols import (
    _SENTENCE_END,
    TranscriptionError,
)
from app.services.remote_transcription import (
    RemoteTranscriptionService,
)
from app.services.segments_builder import (
    build_segments_from_timestamps,
    build_segments_from_vad,
    extract_chunk,
    merge_vad_segments,
    tokens_to_segment,
)

_build_segments_from_timestamps = build_segments_from_timestamps
_build_segments_from_vad = build_segments_from_vad
_extract_chunk = extract_chunk
_merge_vad_segments = merge_vad_segments
_tokens_to_segment = tokens_to_segment

__all__ = [
    "_SENTENCE_END",
    "_build_segments_from_timestamps",
    "_build_segments_from_vad",
    "_extract_chunk",
    "_get_remote_code_path",
    "_merge_vad_segments",
    "_models",
    "_now_iso",
    "_tokens_to_segment",
    "TranscriptionError",
    "TranscriptionModels",
    "RemoteTranscriptionService",
    "build_segments_from_timestamps",
    "build_segments_from_vad",
    "extract_chunk",
    "get_active_engine_config",
    "get_models",
    "is_model_ready",
    "merge_vad_segments",
    "models_initialized",
    "persist_transcript",
    "reset_models",
    "tokens_to_segment",
]
