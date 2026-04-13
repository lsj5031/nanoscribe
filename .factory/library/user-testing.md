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

## Flow Validator Guidance: Browser UI (M2)

### Isolation Rules
- M2 browser assertions involve **upload mutations** (creating memos/jobs).
- Multiple browser validators should NOT run concurrently since they share the database.
- Use a unique browser session ID per validator run.
- After testing, the database will have test memos — this is expected.

### Boundaries
- App URL: http://localhost:8000
- Chromium binary: `/usr/sbin/chromium`
- Test fixtures are in Docker at `/app/data/test-fixtures/`
- The app is running inside Docker on port 8000.

### M2 Upload UI Testing
- Test drag-and-drop from the empty state home page
- Test the file picker upload button
- Verify the processing overlay appears after upload
- Verify the cancel button is visible during processing
- Verify the progress ring renders
- For drag-and-drop testing with agent-browser, use `page.setInputFiles` or CDP drag events

### Key Files
- Upload store: `frontend/src/lib/stores/upload.svelte.ts`
- Processing overlay: `frontend/src/lib/components/ProcessingOverlay.svelte`
- Drop overlay: `frontend/src/lib/components/DropOverlay.svelte`
- Upload page: `frontend/src/routes/+page.svelte`

## Flow Validator Guidance: API Endpoints (M2)

### Isolation Rules for M2
- M2 API assertions **mutate** database state (create memos, jobs).
- API validators that create memos should be run **serially** to avoid interference on shared DB state.
- Each validator should use unique test files/filenames to avoid collision.
- Cleanup: test memos will persist in the DB after testing — this is acceptable.

### Key Endpoints for M2
- `POST /api/memos` — multipart upload with `files[]` field
- `GET /api/memos` — list memos (verify created memos)
- `GET /api/memos/{id}` — get memo detail
- `GET /api/jobs/{id}` — get job status

### Test Fixtures (inside Docker at /app/data/test-fixtures/)
- `test_5s.wav` — 5-second valid WAV (160078 bytes)
- `test_5s.mp3` — 5-second MP3
- `test_5s.m4a` — 5-second M4A
- `test_5s.aac` — 5-second AAC
- `test_5s.webm` — 5-second WebM
- `test_5s.ogg` — 5-second OGG
- `test_5s.opus` — 5-second OPUS
- `test_30s.wav` — 30-second valid WAV
- `corrupt_text.wav` — text file renamed to .wav
- `corrupt_random.wav` — random bytes in .wav
- `empty.mp3` — zero-byte file
- `unsupported.txt` — plain text file
- `unsupported.pdf` — PDF file
- `会议 2026-04-13 (final).mp3` — Unicode/special char filename
- `R&D intro.wav` — Ampersand in filename
- `café recording.ogg` — Accented character in filename

### Upload Response Shape
```json
{
  "memos": [{"id": "...", "title": "...", "source_kind": "upload", "source_filename": "...", "status": "queued", ...}],
  "jobs": [{"id": "...", "memo_id": "...", "job_type": "transcribe", "status": "queued", "progress": 0.0, "attempt_count": 1, ...}],
  "errors": []
}
```
