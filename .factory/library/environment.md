# Environment

Environment variables, external dependencies, and setup notes.

## What belongs here
Required env vars, external API keys/services, dependency quirks, platform-specific notes.

## What does NOT belong here
Service ports/commands (use `.factory/services.yaml`).

---

## Docker Environment

The app runs entirely inside Docker. The base image `glm-asr-glm-asr:latest` provides:
- Python 3.10.12
- PyTorch 2.11.0+cu128
- FunASR 1.3.1
- FastAPI 0.135.2
- uvicorn 0.42.0
- CUDA 13.1 + NVIDIA GPU support

## Required Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `~/.cache/huggingface` | `/home/appuser/.cache/huggingface` | HuggingFace model cache |
| `~/.cache/modelscope` | `/home/appuser/.cache/modelscope` | ModelScope model cache |
| `./data` | `/app/data` | Persistent app data (DB, memos, artifacts) |
| `./frontend` | `/app/frontend` | Frontend source (dev mode) |
| `./backend` | `/app/backend` | Backend source (dev mode) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HF_HUB_OFFLINE` | `0` | Set to 1 to prevent model downloads |
| `MODELSCOPE_CACHE` | `/home/appuser/.cache/modelscope` | ModelScope cache directory |
| `NANOSCRIBE_DATA_DIR` | `/app/data` | App data directory |
| `NANOSCRIBE_HOST` | `0.0.0.0` | Server bind address |
| `NANOSCRIBE_PORT` | `8000` | Server port |

## Model Downloads

First run downloads models (~5 GB total):
- Fun-ASR-Nano-2512 (~2-4 GB ASR model from HuggingFace)
- fsmn-vad (~100 MB VAD model from ModelScope)
- ct-punc (~100 MB punctuation model from ModelScope)
- CAM++ (~30 MB speaker embedding model from ModelScope)

Models are cached in HuggingFace/ModelScope caches and persist across container restarts.

## GPU Requirements

- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed on host
- Minimum 4 GB VRAM recommended (ASR model + diarization model)
- Currently using: NVIDIA GeForce RTX 3070 (8 GB VRAM)
