# FunASR Integration

## Overview

The transcription service (`app/services/transcription.py`) integrates FunASR AutoModel for speech recognition with:
- **ASR**: `FunAudioLLM/Fun-ASR-Nano-2512` — multilingual end-to-end ASR (31 languages)
- **VAD**: `fsmn-vad` — Voice Activity Detection
- **Punc**: `ct-punc` — Punctuation restoration

## Key Technical Details

### Model Loading Quirks

1. **Fun-ASR-Nano requires `trust_remote_code=True`** and explicit `remote_code` path pointing to `funasr/models/fun_asr_nano/model.py`. Without this, the model class `FunASRNano` is not registered.

2. **`openai-whisper` must be installed** — the tokenizer in `fun_asr_nano/model.py` requires it (SenseVoiceTokenizer wraps whisper tokenizer).

3. **Separate model loading (VAD, ASR, Punc)** — Do NOT use the integrated pipeline (passing `vad_model` + `punc_model` to ASR AutoModel). The `inference_with_vad()` method in FunASR 1.3.1 has a bug where it tries `t[0] += vadsegments[j][0]` on dict-based timestamps from Fun-ASR-Nano (expects list `[start, end]` but gets `{"token": ..., "start_time": ..., "end_time": ...}`).

4. **ModelScope cache permissions** — The host mount at `~/.cache/modelscope` may be owned by root. If so, set `MODELSCOPE_CACHE` to a writable directory.

### Output Format

ASR generate() returns:
```json
{
  "key": "filename",
  "text": "Full text with punctuation.",
  "text_tn": "Full text without punctuation",
  "timestamps": [
    {"token": "你", "start_time": 0.48, "end_time": 0.54, "score": 0.992},
    ...
  ],
  "ctc_timestamps": [
    {"token": "你", "start_time": 0.48, "end_time": 0.54, "score": 0.992},
    ...
  ]
}
```

- `timestamps` are in **seconds** (not milliseconds)
- `start_time`/`end_time` per token
- `score` is confidence (0.0-1.0); punctuation tokens have score 0.0

### Segment Building Strategy

1. **Primary**: Token-level timestamps → group by sentence-ending punctuation (。！？.!?)
2. **Fallback**: VAD segment timing → proportional text distribution by character count
3. **Last resort**: Single segment covering full duration

### Hotwords

Pass `hotword` parameter to `model.generate()`. This is a string of comma-separated keywords that improve recognition accuracy for domain-specific terms.

## Environment Variables

- `MODELSCOPE_CACHE` — Override modelscope model cache directory (default: `~/.cache/modelscope`)
- `NANOSCRIBE_DATA_DIR` — App data directory containing memos and DB

## Installed Dependencies

FunASR 1.3.1 and openai-whisper must be installed in the container venv. These are not in pyproject.toml since they're pre-installed in the base Docker image and too large for pip install during normal development.
