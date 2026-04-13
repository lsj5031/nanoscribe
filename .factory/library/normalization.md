# Audio Normalization Service

## Overview

The audio normalization service (`app/services/normalization.py`) handles three key preprocessing steps:

1. **ffmpeg normalization** (`normalize_audio`) - Converts any supported format to canonical WAV: 16-bit PCM, 16kHz, mono
2. **Duration extraction** (`extract_duration_ms`) - Reads WAV header for fast, accurate duration in milliseconds
3. **Waveform peaks** (`extract_waveform_peaks`) - Generates amplitude peak data as JSON array using numpy

## Key Details

- Output files: `normalized.wav` and `waveform.json` stored in memo directory (`/app/data/memos/<id>/`)
- `NormalizationError` is raised for all failure cases (corrupt input, empty file, ffmpeg missing, etc.)
- scipy is available as a dependency (installed in venv) but waveform extraction uses numpy only
- Waveform peaks are ~100 per second of audio, values in [0, 1] range
- Duration accuracy is within ±100ms of ffprobe

## Integration Points

The normalization service is designed to be called during the preprocessing stage of job processing:
1. Upload endpoint creates memo + job + stores `source.original`
2. Worker picks up job → calls `normalize_audio()` → `extract_duration_ms()` → `extract_waveform_peaks()`
3. Updates memo with `duration_ms`
4. Waveform data available for frontend via `waveform.json`

The actual integration into the job worker pipeline will happen in the m3-job-lifecycle feature.
