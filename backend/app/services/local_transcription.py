"""Local FunASR transcription — GPU pipeline with VAD, chunked ASR, punctuation.

Models: Fun-ASR-Nano-2512 (ASR), fsmn-vad (VAD), ct-punc (punctuation).

Pipeline:
  1. Load VAD + ASR + Punc models (lazy, once)
  2. Run VAD on normalized WAV → speech segments [[start_ms, end_ms], ...]
  3. Merge close VAD segments into chunks sized for VRAM
  4. Run ASR on each chunk via ffmpeg extraction
  5. Run Punc restoration on the combined text
  6. Build segments from token timestamps
"""

from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path
from typing import Any, Callable

import structlog

from app.core.config import get_settings
from app.services.protocols import TranscriptionError
from app.services.segments_builder import (
    build_segments_from_timestamps,
    build_segments_from_vad,
    extract_chunk,
    merge_vad_segments,
)

logger = structlog.get_logger(__name__)

_settings = get_settings()
DATA_DIR = _settings.data_dir

ASR_MODEL = _settings.asr_model
VAD_MODEL = _settings.vad_model
PUNC_MODEL = _settings.punc_model

_GIB = 1024**3
_VRAM_AUTO_THRESHOLDS: list[tuple[int, int]] = [
    (20 * _GIB, 120_000),
    (12 * _GIB, 60_000),
    (int(7.5 * _GIB), 30_000),
]
_VRAM_AUTO_FALLBACK_MS = 15_000

_WARM_VRAM_THRESHOLD_BYTES = 5 * _GIB


def _get_remote_code_path() -> str | None:
    """Locate the FunASR Nano model.py for remote_code parameter."""
    try:
        import funasr.models.fun_asr_nano

        model_py = Path(funasr.models.fun_asr_nano.__file__).parent / "model.py"
        if model_py.exists():
            path = str(model_py)
            logger.info("remote_code_path_found", path=path)
            return path
        logger.warning("remote_code_path_missing", searched=str(model_py))
        return None
    except (ImportError, AttributeError):
        logger.warning("remote_code_path_not_locatable")
        return None


class TranscriptionModels:
    """FunASR model manager with GPU inference and optional model caching."""

    def __init__(self) -> None:
        self._device: str = "cpu"
        self._remote_code: str | None = None
        self._loaded: bool = False
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()

        self._vad_model: Any = None
        self._asr_model: Any = None
        self._punc_model: Any = None

        self._max_chunk_ms: int = 30_000
        self._merge_gap_ms: int = 800
        self._chunk_buffer_ms: int = 200
        self._min_chunk_ms: int = 400

        self._keep_warm: bool = False
        self._vram_bytes: int = 0

    # -- Hardware detection ---------------------------------------------------

    def _detect_device(self) -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
        except ImportError:
            pass
        return "cpu"

    def _detect_vram_bytes(self) -> int:
        if not self._device.startswith("cuda"):
            return 0
        try:
            import torch

            return torch.cuda.get_device_properties(self._device).total_memory
        except Exception:
            return 0

    def _auto_max_chunk_ms(self, vram_bytes: int) -> int:
        for threshold, chunk_ms in _VRAM_AUTO_THRESHOLDS:
            if vram_bytes >= threshold:
                return chunk_ms
        return _VRAM_AUTO_FALLBACK_MS

    def _resolve_keep_warm(self, vram_bytes: int) -> bool:
        explicit = _settings.keep_models_warm
        if explicit == "1":
            return True
        if explicit == "0":
            return False
        return vram_bytes >= _WARM_VRAM_THRESHOLD_BYTES

    # -- Model lifecycle -------------------------------------------------------

    def load(self) -> None:
        with self._load_lock:
            if self._loaded:
                return

            if importlib.util.find_spec("funasr") is None:
                raise TranscriptionError("FunASR is not installed")

            self._device = self._detect_device()
            self._remote_code = _get_remote_code_path()
            self._vram_bytes = self._detect_vram_bytes()

            self._merge_gap_ms = _settings.vad_merge_gap_ms
            self._chunk_buffer_ms = _settings.vad_chunk_buffer_ms
            self._min_chunk_ms = _settings.vad_min_chunk_ms

            if _settings.vad_max_chunk_ms > 0:
                self._max_chunk_ms = _settings.vad_max_chunk_ms
            else:
                self._max_chunk_ms = self._auto_max_chunk_ms(self._vram_bytes)

            self._keep_warm = self._resolve_keep_warm(self._vram_bytes)

            vram_gib = f"{self._vram_bytes / (1024**3):.1f} GiB" if self._vram_bytes > 0 else "N/A"
            logger.info(
                "checking_model_cache",
                device=self._device,
                vram=vram_gib,
                max_chunk_ms=self._max_chunk_ms,
                merge_gap_ms=self._merge_gap_ms,
                keep_warm=self._keep_warm,
            )

            missing = []
            for label, model_id in [
                ("VAD", VAD_MODEL),
                ("ASR", ASR_MODEL),
                ("Punc", PUNC_MODEL),
            ]:
                cache_dir = self._model_cache_dir(model_id)
                if cache_dir and not cache_dir.is_dir():
                    missing.append(f"{label} ({model_id})")
                else:
                    logger.info("model_cached", model=label)

            if missing:
                logger.warning("models_not_cached", missing=missing)

            if self._keep_warm and self._device.startswith("cuda"):
                t_warm = time.monotonic()
                self._vad_model = self._create_vad_model()
                logger.info("model_prewarmed", model="VAD")
                self._asr_model = self._create_asr_model()
                logger.info("model_prewarmed", model="ASR")
                self._punc_model = self._create_punc_model()
                logger.info("model_prewarmed", model="Punc")
                logger.info(
                    "models_prewarmed",
                    elapsed_s=round(time.monotonic() - t_warm, 2),
                    max_chunk_ms=self._max_chunk_ms,
                )

            self._loaded = True
            logger.info("pipeline_ready", device=self._device)

    def unload_models(self) -> None:
        if self._vad_model is not None:
            del self._vad_model
            self._vad_model = None
        if self._asr_model is not None:
            del self._asr_model
            self._asr_model = None
        if self._punc_model is not None:
            del self._punc_model
            self._punc_model = None
        self._clear_vram()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def device(self) -> str:
        return self._device

    @staticmethod
    def _model_cache_dir(model_id: str) -> Path | None:
        import os

        cache_root = os.environ.get("MODELSCOPE_CACHE")
        if not cache_root:
            cache_root = str(Path.home() / ".cache" / "modelscope")
        if "/" in model_id:
            org, name = model_id.split("/", 1)
        else:
            return None
        return Path(cache_root) / "models" / org / name

    def _clear_vram(self) -> None:
        if self._device.startswith("cuda"):
            try:
                import torch

                torch.cuda.empty_cache()
            except ImportError:
                pass

    # -- Ephemeral model factories ---------------------------------------------

    def _create_vad_model(self) -> Any:
        from funasr import AutoModel

        kwargs: dict[str, Any] = {
            "model": VAD_MODEL,
            "disable_update": True,
            "model_hub": "modelscope",
            "device": self._device,
        }
        if _settings.offline:
            kwargs["check_latest"] = False
        return AutoModel(**kwargs)

    def _create_asr_model(self) -> Any:
        from funasr import AutoModel

        kwargs: dict[str, Any] = {
            "model": ASR_MODEL,
            "disable_update": True,
            "model_hub": "modelscope",
            "trust_remote_code": True,
            "device": self._device,
        }
        if self._remote_code:
            kwargs["remote_code"] = self._remote_code
        if _settings.offline:
            kwargs["check_latest"] = False
        return AutoModel(**kwargs)

    def _create_punc_model(self) -> Any:
        from funasr import AutoModel

        kwargs: dict[str, Any] = {
            "model": PUNC_MODEL,
            "disable_update": True,
            "model_hub": "modelscope",
            "device": self._device,
        }
        if _settings.offline:
            kwargs["check_latest"] = False
        return AutoModel(**kwargs)

    # -- Model cache helpers ---------------------------------------------------

    def _get_vad_model(self) -> Any:
        if self._keep_warm and self._vad_model is not None:
            return self._vad_model
        model = self._create_vad_model()
        if self._keep_warm:
            self._vad_model = model
        return model

    def _get_asr_model(self) -> Any:
        if self._keep_warm and self._asr_model is not None:
            return self._asr_model
        model = self._create_asr_model()
        if self._keep_warm:
            self._asr_model = model
        return model

    def _get_punc_model(self) -> Any:
        if self._keep_warm and self._punc_model is not None:
            return self._punc_model
        model = self._create_punc_model()
        if self._keep_warm:
            self._punc_model = model
        return model

    def _maybe_drop_vad(self) -> None:
        if not self._keep_warm:
            self._vad_model = None
            self._clear_vram()

    def _maybe_drop_asr(self) -> None:
        if not self._keep_warm:
            self._asr_model = None
            self._clear_vram()

    def _maybe_drop_punc(self) -> None:
        if not self._keep_warm:
            self._punc_model = None
            self._clear_vram()

    # -- Inference methods -----------------------------------------------------

    def run_vad(self, audio_path: str | Path) -> list[list[int]]:
        if not self._loaded:
            raise TranscriptionError("Models not loaded — call load() first")

        logger.info("vad_start", audio=str(audio_path), device=self._device)
        t0 = time.monotonic()

        with self._infer_lock:
            model = self._get_vad_model()
            try:
                result = model.generate(input=str(audio_path))
                if not result or not result[0].get("value"):
                    logger.info("vad_done", segments=0, elapsed_s=round(time.monotonic() - t0, 2))
                    return []
                segments = result[0]["value"]
                logger.info(
                    "vad_done",
                    segments=len(segments),
                    total_speech_ms=sum(e - s for s, e in segments),
                    elapsed_s=round(time.monotonic() - t0, 2),
                )
                return segments
            except Exception as exc:
                logger.error("vad_failed", error=str(exc))
                raise TranscriptionError(f"VAD processing failed: {exc}") from exc
            finally:
                self._maybe_drop_vad()

    def run_asr_chunked(
        self,
        audio_path: str | Path,
        vad_segments: list[list[int]],
        hotwords: str | None = None,
        chunk_callback: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        if not vad_segments:
            return []

        merged = merge_vad_segments(
            vad_segments,
            gap_threshold_ms=self._merge_gap_ms,
            max_duration_ms=self._max_chunk_ms,
        )
        logger.info(
            "chunked_asr_start",
            raw_segments=len(vad_segments),
            merged_segments=len(merged),
            max_chunk_ms=self._max_chunk_ms,
            device=self._device,
        )

        all_results: list[dict[str, Any]] = []
        t_chunk_total = time.monotonic()

        with self._infer_lock:
            t_model_load = time.monotonic()
            model = self._get_asr_model()
            logger.info("asr_model_loaded", load_s=round(time.monotonic() - t_model_load, 2))
            try:
                for i, (start_ms, end_ms) in enumerate(merged):
                    t_chunk_start = time.monotonic()
                    chunk_info = extract_chunk(
                        audio_path,
                        start_ms,
                        end_ms,
                        buffer_ms=self._chunk_buffer_ms,
                        min_chunk_ms=self._min_chunk_ms,
                    )
                    if chunk_info is None:
                        logger.warning(
                            "chunk_skipped_too_short",
                            chunk_index=i,
                            start_ms=start_ms,
                            end_ms=end_ms,
                        )
                        continue
                    chunk_path, padded_start = chunk_info
                    logger.debug(
                        "chunk_extracted",
                        chunk_index=i,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        padded_start_ms=padded_start,
                        chunk_path=str(chunk_path),
                    )

                    try:
                        generate_kwargs: dict[str, Any] = {
                            "input": str(chunk_path),
                            "disable_pbar": True,
                        }
                        if hotwords:
                            generate_kwargs["hotword"] = hotwords

                        chunk_result = model.generate(**generate_kwargs)
                    except Exception as exc:
                        logger.warning(
                            "chunk_asr_failed",
                            chunk_index=i,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            error=str(exc),
                        )
                        continue
                    finally:
                        try:
                            chunk_path.unlink()
                        except OSError:
                            pass

                    if not chunk_result:
                        continue

                    result = chunk_result[0]
                    offset_s = padded_start / 1000.0
                    timestamps = result.get("timestamps", [])
                    for ts in timestamps:
                        ts["start_time"] = round(ts.get("start_time", 0) + offset_s, 3)
                        ts["end_time"] = round(ts.get("end_time", 0) + offset_s, 3)

                    all_results.append(result)

                    chunk_text = result.get("text", "")
                    n_tokens = len(timestamps)
                    logger.info(
                        "chunk_done",
                        chunk_index=i + 1,
                        total_chunks=len(merged),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        tokens=n_tokens,
                        text_preview=chunk_text[:60] if chunk_text else "",
                        elapsed_s=round(time.monotonic() - t_chunk_start, 2),
                    )

                    if chunk_callback is not None:
                        try:
                            chunk_callback(i + 1, len(merged))
                        except Exception:
                            pass
            finally:
                self._maybe_drop_asr()

        total_elapsed = time.monotonic() - t_chunk_total
        logger.info(
            "chunked_asr_done",
            chunks_processed=len(all_results),
            total_tokens=sum(len(r.get("timestamps", [])) for r in all_results),
            elapsed_s=round(total_elapsed, 2),
        )

        return all_results

    def run_punc(self, text: str) -> str:
        if not self._loaded:
            raise TranscriptionError("Models not loaded — call load() first")

        logger.info("punc_start", text_length=len(text))
        t0 = time.monotonic()

        with self._infer_lock:
            model = self._get_punc_model()
            try:
                result = model.generate(input=text)
                if result and result[0].get("text"):
                    punc_text = result[0]["text"]
                    logger.info("punc_done", elapsed_s=round(time.monotonic() - t0, 2))
                    return punc_text
                logger.info("punc_done", result="unchanged", elapsed_s=round(time.monotonic() - t0, 2))
                return text
            except Exception as exc:
                logger.warning("punc_failed", error=str(exc))
                return text
            finally:
                self._maybe_drop_punc()

    def transcribe(
        self,
        audio_path: str | Path,
        hotwords: str | None = None,
        chunk_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        self.load()

        logger.info("transcribe_start", audio=str(audio_path), hotwords=hotwords)
        t0 = time.monotonic()

        vad_segments = self.run_vad(audio_path)

        if not vad_segments:
            logger.info("transcribe_done", result="no_speech", elapsed_s=round(time.monotonic() - t0, 2))
            return {"raw_output": [], "text": "", "segments": []}

        chunk_results = self.run_asr_chunked(audio_path, vad_segments, hotwords=hotwords, chunk_callback=chunk_callback)

        if not chunk_results:
            logger.info("transcribe_done", result="no_asr_output", elapsed_s=round(time.monotonic() - t0, 2))
            return {"raw_output": [], "text": "", "segments": []}

        all_timestamps: list[dict[str, Any]] = []
        all_raw_text: list[str] = []
        all_punct_text: list[str] = []

        for result in chunk_results:
            raw_text = result.get("text_tn", result.get("text", "")).strip()
            punct_text = result.get("text", "").strip()
            if raw_text:
                all_raw_text.append(raw_text)
            if punct_text:
                all_punct_text.append(punct_text)
            timestamps = result.get("timestamps", [])
            if timestamps:
                all_timestamps.extend(timestamps)

        combined_raw = " ".join(all_raw_text)
        combined_punct = " ".join(all_punct_text)

        if combined_raw:
            combined_punct = self.run_punc(combined_raw)

        if all_timestamps:
            segments = build_segments_from_timestamps(all_timestamps)
            logger.info("segments_built", method="timestamps", count=len(segments))
        elif vad_segments:
            segments = build_segments_from_vad(vad_segments, combined_punct or combined_raw)
            logger.info("segments_built", method="vad_fallback", count=len(segments))
        else:
            segments = [
                {
                    "start_ms": 0,
                    "end_ms": 0,
                    "text": combined_punct or combined_raw,
                    "confidence": 1.0,
                }
            ]
            logger.info("segments_built", method="fallback", count=1)

        combined_text = " ".join(str(seg["text"]) for seg in segments if str(seg["text"]).strip())

        logger.info(
            "transcribe_done",
            segment_count=len(segments),
            text_length=len(combined_text),
            elapsed_s=round(time.monotonic() - t0, 2),
        )

        return {
            "raw_output": chunk_results,
            "text": combined_text,
            "segments": segments,
        }
