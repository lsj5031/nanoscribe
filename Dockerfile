# syntax=docker/dockerfile:1.7
#
# NanoScribe — multi-stage build.
#
# Default base is the public NVIDIA CUDA 12.4 runtime image so the build is
# reproducible by anyone with Docker + nvidia-container-toolkit.
#
# Power users can override the base with a pre-baked image that already has
# /app/venv populated:
#     docker build --build-arg BASE_IMAGE=my/own:tag --build-arg SKIP_BASE=1 ...
#
ARG BASE_IMAGE=nvidia/cuda:12.4.1-runtime-ubuntu22.04
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124

# ---------------------------------------------------------------------------
# Stage 1: system — Ubuntu + CUDA + Python 3.10 + ffmpeg + appuser + venv
# Replicates everything the previous private base image provided.
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS system

ARG TORCH_INDEX_URL

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# System packages: Python 3.10, ffmpeg, build essentials, audio libs, git, curl.
# Use Ubuntu's default Python 3.10 from 22.04 (matches the previous base).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git \
        python3 python3-venv python3-pip python3-dev \
        build-essential pkg-config \
        ffmpeg libsndfile1 \
        && ln -sf /usr/bin/python3 /usr/bin/python \
        && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (uid 1000), matching the previous base contract.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser \
    && mkdir -p /app /app/data \
    && chown -R appuser:appuser /app

# Create the venv at /app/venv (hard-coded in compose / Makefile / docs).
RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --upgrade pip wheel setuptools \
    && chown -R appuser:appuser /app/venv

# CUDA-enabled PyTorch + torchaudio (must come before FunASR/pyannote so the
# CUDA wheels are not pulled twice with conflicting versions).
RUN /app/venv/bin/pip install \
        --index-url ${TORCH_INDEX_URL} \
        torch==2.5.1 torchaudio==2.5.1

# Lightweight web/runtime deps that the previous base bundled.
RUN /app/venv/bin/pip install \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "sse-starlette>=2.1" \
        "httpx>=0.27" \
        "pydantic>=2" \
        "scipy>=1.10" \
        "structlog>=24.0.0" \
        "soundfile>=0.12" \
        "pydub>=0.25" \
        "ffmpeg-python>=0.2" \
        "python-multipart>=0.0.12" \
        "numpy<2.0.0"

ENV PATH="/app/venv/bin:${PATH}" \
    VIRTUAL_ENV=/app/venv \
    NANOSCRIBE_DATA_DIR=/app/data

# ---------------------------------------------------------------------------
# Stage 2: ml-deps — FunASR, ModelScope, pyannote, 3D-Speaker
# Heavy ML packages live in their own layer for cache-friendliness.
# ---------------------------------------------------------------------------
FROM system AS ml-deps

USER root

RUN /app/venv/bin/pip install \
        funasr \
        modelscope \
        tiktoken \
        addict>=2.4.0 \
        datasets>=4.0.0 \
        "scikit-learn>=1.3" \
        kaldiio \
        pyyaml \
        pandas \
        openpyxl \
        "pyannote.audio==3.1.1" \
        umap-learn \
        hdbscan \
        fastcluster \
        "simplejson>=3.19" \
    && /app/venv/bin/pip uninstall -y torchcodec || true

# 3D-Speaker for diarization. Backend probes /opt/3D-Speaker at runtime
# (see backend/app/services/diarization.py).
# We deliberately do NOT install its requirements.txt — it pins numpy<1.24
# and scikit-learn==1.0.2 which conflict with pyannote.audio.
RUN git clone --depth 1 https://github.com/modelscope/3D-Speaker.git /opt/3D-Speaker

# ---------------------------------------------------------------------------
# Stage 3: dev — adds Node.js, pnpm, and Python dev tools (ruff, ty, pytest)
# Used by `make dev` / docker-compose for hot-reload development.
# ---------------------------------------------------------------------------
FROM ml-deps AS dev

USER root

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && rm -rf /var/lib/apt/lists/*

RUN /app/venv/bin/pip install \
        ruff \
        ty \
        pytest \
        pytest-asyncio \
        httpx

USER appuser
WORKDIR /app/backend

COPY --chown=appuser:appuser backend/ /app/backend/
COPY --chown=appuser:appuser frontend/ /app/frontend/

RUN cd /app/backend && /app/venv/bin/pip install --no-cache-dir -e ".[dev]" || true
RUN cd /app/frontend && pnpm install --frozen-lockfile 2>/dev/null || pnpm install || true

ENV HF_HUB_OFFLINE=0 \
    MODELSCOPE_CACHE=/home/appuser/.cache/modelscope \
    NANOSCRIBE_OFFLINE=0

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Stage 4: frontend-build — build the SvelteKit SPA
# Kept separate so the production image doesn't carry Node/pnpm.
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend-build

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

# ---------------------------------------------------------------------------
# Stage 5: production — lean runtime: ML deps + backend + built SPA
# This is the image published to GHCR.
# ---------------------------------------------------------------------------
FROM ml-deps AS production

USER root
WORKDIR /app/backend

COPY --chown=appuser:appuser backend/ /app/backend/
RUN cd /app/backend && /app/venv/bin/pip install --no-cache-dir .

# Built SPA — served by FastAPI as static files.
COPY --from=frontend-build --chown=appuser:appuser /app/frontend/build /app/static

USER appuser

ENV PATH="/app/venv/bin:${PATH}" \
    HF_HUB_OFFLINE=0 \
    MODELSCOPE_CACHE=/app/data/.modelscope_cache \
    NANOSCRIBE_DATA_DIR=/app/data \
    NANOSCRIBE_STATIC_DIR=/app/static \
    NANOSCRIBE_OFFLINE=0 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/system/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
