ARG BASE_IMAGE=glm-asr-glm-asr:latest

# ---------------------------------------------------------------------------
# Stage 1: dev – adds Node.js, pnpm, and Python dev tools
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS dev

USER root

# Install Node.js 22.x (LTS) and pnpm
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && rm -rf /var/lib/apt/lists/*

# Install FunASR and Python dev tools into the existing venv
RUN /app/venv/bin/pip install --no-cache-dir \
    funasr \
    modelscope \
    tiktoken \
    structlog>=24.0.0 \
    addict>=2.4.0 \
    datasets>=4.0.0 \
    "numpy<2.0.0" \
    "scikit-learn>=1.3" \
    soundfile \
    kaldiio \
    pyyaml \
    pandas \
    openpyxl \
    pyannote.audio==3.1.1 \
    umap-learn \
    hdbscan \
    fastcluster \
    simplejson>=3.19 \
    && /app/venv/bin/pip uninstall -y torchcodec || true

# 3D-Speaker for speaker diarization
# NOTE: Do NOT install 3D-Speaker's requirements.txt — it pins
# numpy<1.24 and scikit-learn==1.0.2 which conflict with pyannote.audio.
# The dependencies above provide everything 3D-Speaker needs.
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/* && \
    git clone https://github.com/modelscope/3D-Speaker.git /opt/3D-Speaker

RUN /app/venv/bin/pip install --no-cache-dir \
    ruff \
    ty \
    pytest \
    pytest-asyncio \
    httpx

USER appuser
WORKDIR /app/backend

# Copy backend and frontend source (overridden by bind mounts in dev)
COPY --chown=appuser:appuser backend/ /app/backend/
COPY --chown=appuser:appuser frontend/ /app/frontend/

# Install backend as editable package
RUN cd /app/backend && /app/venv/bin/pip install --no-cache-dir -e ".[dev]" || true

# Install frontend dependencies
RUN cd /app/frontend && pnpm install --frozen-lockfile 2>/dev/null || pnpm install || true

ENV PATH="/app/venv/bin:${PATH}" \
    HF_HUB_OFFLINE=0 \
    MODELSCOPE_CACHE=/home/appuser/.cache/modelscope \
    NANOSCRIBE_DATA_DIR=/app/data \
    NANOSCRIBE_OFFLINE=0

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Stage 2: builder – installs deps and builds the SPA
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS builder

USER root

# Install Node.js 22.x and pnpm for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && rm -rf /var/lib/apt/lists/*

USER appuser
WORKDIR /app

# Copy frontend and build static SPA
COPY --chown=appuser:appuser frontend/ /app/frontend/
RUN cd /app/frontend && pnpm install --frozen-lockfile 2>/dev/null || pnpm install \
    && pnpm build

# Copy backend and install
COPY --chown=appuser:appuser backend/ /app/backend/
RUN cd /app/backend && /app/venv/bin/pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Stage 3: production – lean image with built SPA + FastAPI
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS production

USER appuser
WORKDIR /app/backend

# Copy installed backend from builder
COPY --from=builder --chown=appuser:appuser /app/backend /app/backend
COPY --from=builder --chown=appuser:appuser /app/venv /app/venv

# Copy built SPA for static serving
COPY --from=builder --chown=appuser:appuser /app/frontend/build /app/static

ENV PATH="/app/venv/bin:${PATH}" \
    HF_HUB_OFFLINE=0 \
    MODELSCOPE_CACHE=/home/appuser/.cache/modelscope \
    NANOSCRIBE_DATA_DIR=/app/data \
    NANOSCRIBE_OFFLINE=0

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
