# User Testing

Testing surface, required testing skills/tools, and resource cost classification per surface.

## Validation Surface

### Browser UI
- **Tool:** agent-browser (Playwright + Chromium)
- **Setup:** App must be running inside Docker on port 8000
- **Scope:** Library, editor, recording, settings, export, drag-drop, keyboard navigation
- **Notes:** Chromium is at `/usr/sbin/chromium`, Playwright 1.59.1 available

### API Endpoints
- **Tool:** curl / pytest
- **Setup:** App must be running inside Docker on port 8000
- **Scope:** All `/api/*` endpoints - system, memos, segments, speakers, jobs, search, export

### Job Processing
- **Tool:** pytest with real audio samples
- **Setup:** App running with GPU access, models downloaded
- **Scope:** Transcription pipeline, diarization, job lifecycle, error handling

## Validation Concurrency

### Browser UI
- **Max concurrent validators:** 3
- **RAM per browser instance:** ~1.5-2.5 GB
- **Available RAM:** ~10 GiB (15 GiB total, ~5 GiB baseline)
- **Rationale:** Using 70% of available headroom: 10 GB * 0.7 = 7 GB. 3 instances * ~2 GB = 6 GB (fits). 4 instances * 2 GB = 8 GB (too close to limit with app overhead).

### API Endpoints
- **Max concurrent validators:** 5 (lightweight, no meaningful resource cost)

### Job Processing
- **Max concurrent validators:** 1 (GPU-bound, single job queue)

## Test Audio Fixtures

Validators will need test audio files:
- Short valid audio (~5s, multiple formats: wav, mp3, m4a, webm, ogg)
- Medium valid audio (~30s-2min, for transcription testing)
- Multi-speaker audio (for diarization testing)
- Corrupt files (zero-byte, renamed text file, truncated media)
- Unsupported format files (.txt, .pdf, .avi)
- Large file (~100MB, for upload handling)

## Flow Validator Guidance: API Endpoints

### Isolation Rules
- All assertions in this group are **read-only** (GET requests to system endpoints and code inspection).
- No mutations to database or filesystem state.
- Multiple API validators can run concurrently without conflict.
- The app is running inside Docker on port 8000 (http://localhost:8000).

### Shared State
- All validators share the same running app instance.
- Database is the same for all validators (read-only access only).
- No test data seeding needed for M1 system endpoint tests.

### Key Endpoints for M1
- `GET /api/system/capabilities` — returns JSON capability manifest
- `GET /api/system/health` — returns JSON health status
- `GET /` — returns frontend HTML (200)
- `GET /settings` — returns frontend HTML (200, SPA catch-all)
- `GET /api` — behavior varies (may return 404 or SPA catch-all)

### Code Inspection Notes
- FTS5 migrations: `backend/app/db/migrations/001_initial_schema.sql` and `002_fix_fts5_segment_triggers.sql`
- SPA serving: `backend/app/main.py`
- Frontend built at `/app/frontend/build/`, symlinked to `/app/static/` in dev mode

## Flow Validator Guidance: Browser UI

### Isolation Rules
- M1 browser assertions are **read-only visual checks** (no mutations).
- Only need one browser instance.
- No test data seeding needed.
- Session ID for agent-browser: `5b8b5af1dd95`

### Boundaries
- App URL: http://localhost:8000
- Chromium binary: `/usr/sbin/chromium`
- Do NOT interact with upload, recording, or editing features (not tested in M1).
- Only verify visual appearance (dark mode, accent color).

### Visual Checks
- Dark mode: verify dark background on body/root element, light text, dark cards
- Teal accent: verify #00d4ff appears in CSS custom properties, Tailwind tokens, or computed styles
