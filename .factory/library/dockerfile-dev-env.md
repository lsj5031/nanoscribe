# Dockerfile & Dev Environment Setup

## What was implemented

Multi-stage Docker build (dev + production) with FastAPI backend skeleton serving both frontend SPA and /api/* endpoints.

## Key Files

- `Dockerfile` - Multi-stage: dev (Node.js 22, pnpm, ruff, ty, pytest) + builder + production
- `docker-compose.yml` - Dev mode with bind mounts for backend/ and frontend/, port 8000
- `backend/app/main.py` - FastAPI app factory with SPA serving and /api routes
- `backend/app/api/system.py` - GET /api/system/health endpoint
- `backend/pyproject.toml` - Backend package config with ruff, ty, pytest settings

## Container Layout

```
/app/backend/        # FastAPI app (app.main:app)
/app/frontend/       # SvelteKit frontend source
/app/data/           # Persistent data (bind-mounted)
  nanoscribe.db      # SQLite database
  memos/             # Memo artifacts
/app/static/         # Built SPA (production only)
/app/venv/           # Python virtualenv (from base image)
```

## Running the Dev Environment

```bash
# Build dev image
make build-dev

# Start dev server (port 8000 or set HOST_PORT)
HOST_PORT=8976 docker compose up -d

# Run tests
docker compose exec funasr bash -c "cd /app/backend && python -m pytest tests/ -x"

# Quality checks
docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check . && ty check ."

# Shell access
docker compose exec funasr bash
```

## Port Note

Port 8000 is the internal container port. If it conflicts on the host, use `HOST_PORT=8976` (or any available port). The spec says host port 8976 is the mapping target.

## Working Directory

The container WORKDIR is `/app/backend` so uvicorn finds `app.main:app` correctly.

## Static File Serving

In dev mode: root `/` returns an HTML placeholder (no SPA built yet).
In production: root `/` serves the built SvelteKit SPA from `/app/static/`.
API routes are always under `/api/*` prefix.
