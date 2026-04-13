# NanoScribe User Testing Knowledge Base

## Validation Surfaces

### API (curl)
- Base URL: `http://localhost:8000`
- Health: `GET /api/system/health`
- Capabilities: `GET /api/system/capabilities`
- Upload: `POST /api/memos` (multipart, `files[]`)
- Job snapshot: `GET /api/jobs/{id}`
- Job events: `GET /api/jobs/{id}/events` (SSE)
- Cancel: `POST /api/jobs/{id}/cancel`
- Retry: `POST /api/memos/{id}/retry`
- Reprocess: `POST /api/memos/{id}/reprocess`
- Memo list: `GET /api/memos` (paginated)

### Browser (agent-browser)
- Not needed for m3-transcription (all assertions are API/test based)

## Environment Setup

1. App runs inside Docker: `docker compose up -d`
2. Container must have FunASR + tiktoken installed (Dockerfile dev stage)
3. Models download on first transcription (~5GB from ModelScope)
4. MODELSCOPE_CACHE must point to a writable directory (e.g., `/app/data/.modelscope_cache`)
5. Test fixtures in `/app/data/test-fixtures/`: `test_5s.wav` (5s), `test_30s.wav` (30s), etc.
6. GPU available via NVIDIA Container Toolkit

## Known Quirks

- First transcription takes 2-3 minutes (model download + GPU warmup)
- Subsequent transcriptions are fast (~5-10s for 5s audio, ~30s for 30s audio)
- `GET /api/memos/{id}` endpoint not yet implemented (m4-library) — use DB queries instead
- `GET /api/memos/{id}/jobs` endpoint not yet implemented (route missing from router) — use DB queries
- SSE reconnect sends current state as `job.state` event, not replay
- Progress updates during transcription jump to 0.7 then to 1.0 (batch ASR processing)
- Timestamps use malformed format `%Y-%m-%dT%H:%M:%fZ` (bug: missing `%S.` before `%f`)
- GET /api/jobs/{id} response missing `updated_at` field (schema gap)
- Dockerfile needs `funasr`, `modelscope`, and `tiktoken` pip-installed in venv (base image doesn't include them)
- MODELSCOPE_CACHE must point to writable directory (host mount may be root-owned)
- `_get_remote_code_path()` must use package `__file__` not `import model` (model.py has import-time dependency on `ctc` module)

## Validation Concurrency

- **API surface**: Max 5 concurrent validators (lightweight, no browser)
- **Transcription is serialized**: Only one GPU job at a time, so test upload timing carefully
- **Job state assertions share global state**: Cancel/retry assertions must run sequentially

## Flow Validator Guidance: API

### Isolation Rules
- Each validator group should use its own memo/job IDs
- Cancel and retry assertions mutate job state — group them together
- Upload new files for each assertion group to avoid cross-contamination
- Do not delete memos used by other groups

### Shared State Boundaries
- The worker queue is global (one GPU job at a time)
- The database is shared across all groups
- SSE manager is global
- Test fixture files are read-only and safe to share
