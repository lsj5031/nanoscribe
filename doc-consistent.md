# Documentation Consistency Audit Report

> **Project:** NanoScribe
> **Audit Date:** 2025-07-09
> **Scope:** README.md, SPEC.md, .env.example vs. backend code, frontend code, DB schema, Docker configs, CI workflow
> **Methodology:** Code is Truth; every finding cites specific file paths and line numbers.

---

## Audit Verdict

- **Result**: CONDITIONAL PASS
- **Stats**: P0: 1, P1: 6, P2: 17, P3: 5, Needs Evidence: 2
- **Total unique discrepancies**: 31
- **Priority**: Fix the Docker HEALTHCHECK (P0) immediately. Address P1 items before next release.

---

## P0 — Blocker

### [01] Docker HEALTHCHECK targets non-existent path
- **Severity**: P0 (Blocker)
- **Location**: `Dockerfile:186` vs `backend/app/api/system.py:42`
- **Evidence**:
  - *Doc/Config Claim*: Dockerfile production stage HEALTHCHECK: `CMD curl -fsS http://localhost:8000/health || exit 1`
  - *Code Reality*: The health endpoint is at `/api/system/health`, not `/health`. The route is registered with `prefix="/api/system"` in `main.py:86`. There is no `/health` route.
- **Impact**: Production Docker containers will be marked unhealthy by Docker, causing orchestration failures and automatic restarts.
- **Recommendation**: Change HEALTHCHECK to `CMD curl -fsS http://localhost:8000/api/system/health || exit 1`.
- **Principle**: Code as Truth

---

## P1 — Major

### [02] SPEC capability manifest missing `streaming_partial_transcript` field
- **Severity**: P1 (Major)
- **Location**: `SPEC.md:§12` vs `backend/app/schemas/system.py:28-37`
- **Evidence**:
  - *Doc Claim*: SPEC §12 capability manifest lists `streaming_partial_transcript`
  - *Code Reality*: `CapabilitiesResponse` schema has exactly 10 fields: `ready, gpu, device, asr_model, vad, timestamps, speaker_diarization, hotwords, language_auto_detect, recording`. No `streaming_partial_transcript` field exists. SPEC §3.1 and §29 also reference "partial transcript streaming" / "partial transcript updates" — these are not implemented.
- **Impact**: Clients expecting this field would receive a validation error. The SSE stream exposes job progress events only, not partial transcript chunks.
- **Recommendation**: Remove `streaming_partial_transcript` from SPEC §§3.1, §12, and §29, or implement partial transcript streaming and add the field.
- **Principle**: Code as Truth

### [03] SPEC Claims `tailwind.config.ts` exists but file is absent
- **Severity**: P1 (Major)
- **Location**: `SPEC.md:§8` vs `frontend/`
- **Evidence**:
  - *Doc Claim*: SPEC §8 Repository Target Structure shows `frontend/tailwind.config.ts`
  - *Code Reality*: No `tailwind.config.ts` file exists. The frontend uses hand-written CSS, not Tailwind.
- **Impact**: Developers following the SPEC to set up Tailwind configuration would waste time looking for a file that doesn't exist.
- **Recommendation**: Remove `tailwind.config.ts` from SPEC §8 or add Tailwind configuration.
- **Principle**: Code as Truth

### [04] SPEC claims `workers/` directory under `backend/app/`
- **Severity**: P1 (Major)
- **Location**: `SPEC.md:§8` vs actual project structure
- **Evidence**:
  - *Doc Claim*: SPEC §8 Repository Target Structure shows `backend/app/workers/`
  - *Code Reality*: Worker logic lives in `backend/app/services/worker.py`, not a separate `workers/` directory.
- **Impact**: Misleading for new developers navigating the codebase.
- **Recommendation**: Update SPEC §8 to reflect actual structure: `services/worker.py` instead of `workers/`.
- **Principle**: Code as Truth

### [05] README env var table missing VAD/chunking/warm-model env vars
- **Severity**: P1 (Major)
- **Location**: `README.md:§Environment Variables` vs `backend/app/core/config.py:40-48`
- **Evidence**:
  - *Doc Claim*: README env var table documents 12 variables
  - *Code Reality*: `config.py` defines 6 additional env vars not documented in README: `NANOSCRIBE_VAD_MAX_CHUNK_MS`, `NANOSCRIBE_VAD_MERGE_GAP_MS`, `NANOSCRIBE_VAD_CHUNK_BUFFER_MS`, `NANOSCRIBE_VAD_MIN_CHUNK_MS`, `NANOSCRIBE_KEEP_MODELS_WARM`, `NANOSCRIBE_REMOTE_ASR_TIMEOUT`
- **Impact**: Power users cannot tune VAD chunking, warm-caching, or remote timeout behavior without reading source code.
- **Recommendation**: Add all environment variables to the README table.
- **Principle**: Code as Truth

### [06] SPEC design accent color differs from frontend implementation
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§22.1` vs `frontend/src/routes/memos/[memoId]/+page.svelte`
- **Evidence**:
  - *Doc Claim*: SPEC §22.1 says "Strong teal primary accent `#00d4ff`"
  - *Code Reality*: The frontend uses gold `#D4AF37` as the accent color throughout. Teal `#00d4ff` is used only for the PWA theme color and some status indicators.
- **Impact**: UI/UX inconsistency — the design spec describes one visual identity but the code implements another.
- **Recommendation**: Either update SPEC §22.1 to reflect the gold accent, or update the frontend to use teal.
- **Principle**: Code as Truth

### [07] SPEC storage layout shows `diarization.json` — not created by code
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§9` vs `README.md:§Storage Layout`
- **Evidence**:
  - *Doc Claim*: SPEC §9 Storage Layout shows `diarization.json` in the memo directory
  - *Code Reality*: Diarization results are written to the database (`memo_speakers` table in `db/migrations/`) and merged into `transcript.final.json`. No standalone `diarization.json` is created.
- **Impact**: Confusion about whether diarization data is file-based or DB-based.
- **Recommendation**: Remove `diarization.json` from SPEC §9 storage layout.
- **Principle**: Code as Truth

### [08] Frontend settings (hotwords, language) stored in localStorage but never sent to API
- **Severity**: P1 (Major)
- **Location**: `frontend/src/lib/stores/settings.svelte.ts:1-3` vs `backend/app/api/memos.py:24-32`
- **Evidence**:
  - *Doc Claim*: SPEC §20 describes functional settings: "Toggle diarization by default", "Set language to auto or specific language", "Enter hotwords"
  - *Code Reality*: `settings.svelte.ts` comment states "Hotwords and language are stored locally; actual API integration is future work." The upload form in `memos.py` accepts `language`, `enable_diarization`, and `hotwords` as form parameters, but the frontend upload flow never sends them.
- **Impact**: User-configured hotwords and language preferences in Settings have no effect on transcription. The Settings page is a facade.
- **Recommendation**: Wire the settings store values to the upload/reprocess API calls.
- **Principle**: User Promise First

### [09] CI skips GPU-dependent tests without documenting the omission
- **Severity**: P1 (Major)
- **Location**: `.github/workflows/check.yml:41` vs `README.md:§Testing`
- **Evidence**:
  - *Doc Claim*: README says `make check` runs "Full local verification suite (Docker-backed)" implying full test coverage
  - *Code Reality*: CI `pytest` invocation explicitly ignores GPU tests: `pytest -q --ignore=tests/test_transcription.py --ignore=tests/test_diarization.py`. These tests are never run in CI. The README Testing section doesn't mention this.
- **Impact**: Contributors running local `make check` get different results than CI. A broken transcription or diarization test won't be caught by the CI pipeline.
- **Recommendation**: Document in README §Testing that CI skips GPU-dependent tests, or add a GPU-enabled CI job.
- **Principle**: Code as Truth

---

## P2 — Minor

### [10] Bot service mounts telegram-api-data volume unnecessarily
- **Severity**: P2 (Minor)
- **Location**: `docker-compose.yml:60` vs `compose.run.yml:62`
- **Evidence**:
  - *Doc/Config Claim*: `docker-compose.yml` bot service mounts `telegram-api-data:/var/lib/telegram-bot-api:ro`
  - *Code Reality*: The bot service does not need access to `/var/lib/telegram-bot-api`. This volume is for the `telegram-api` service. `compose.run.yml` does NOT mount this volume on the bot service. The `:ro` flag makes this harmless but confusing.
- **Impact**: Dev environment has an unnecessary and potentially confusing volume mount. Inconsistency between dev and run compose files.
- **Recommendation**: Remove `telegram-api-data:/var/lib/telegram-bot-api:ro` from the bot service in `docker-compose.yml`.
- **Principle**: Code as Truth

### [11] Frontend stores count differs from SPEC
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§24.1` vs `frontend/src/lib/stores/`
- **Evidence**:
  - *Doc Claim*: SPEC §24.1 lists 6 stores
  - *Code Reality*: 11 store files exist: `api.svelte.ts`, `capabilities.svelte.ts`, `editor.svelte.ts`, `library.svelte.ts`, `readiness.svelte.ts`, `recording.svelte.ts`, `search.svelte.ts`, `settings.svelte.ts`, `system-status.svelte.ts`, `toasts.svelte.ts`, `upload.svelte.ts`
- **Impact**: 5 stores (api, readiness, search, system-status, toasts, upload) are not documented in the state model section.
- **Recommendation**: Update SPEC §24.1 to include all stores.
- **Principle**: Code as Truth

### [12] SPEC backend services list incomplete
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§25` vs `backend/app/services/`
- **Evidence**:
  - *Doc Claim*: SPEC §25 lists 8 services
  - *Code Reality*: `services/` directory contains 16 Python files including `sse.py`, `worker.py`, `capabilities.py`, `status.py`, `speakers.py`, `segments.py`, `jobs.py`, `upload.py`, `library.py`, `diarization.py` — many not listed in SPEC.
- **Impact**: Incomplete architecture documentation.
- **Recommendation**: Update SPEC §25 to match actual service modules.
- **Principle**: Code as Truth

### [13] .env.example is bot-focused, lacks app configuration template
- **Severity**: P2 (Minor)
- **Location**: `.env.example:1-12` vs `backend/app/core/config.py`
- **Evidence**:
  - *Doc Claim*: `.env.example` describes "NanoScribe (existing)" section with `HOST_PORT` and `BASE_IMAGE` as placeholders
  - *Code Reality*: `HOST_PORT` and `BASE_IMAGE` are Docker/build-time vars, not app config. The actual app env vars (`NANOSCRIBE_API_KEY`, `NANOSCRIBE_REMOTE_ASR_URL`, `NANOSCRIBE_OFFLINE`, `NANOSCRIBE_KEEP_MODELS_WARM`, etc.) are not shown.
- **Impact**: Users copying `.env.example` won't discover available application environment variables.
- **Recommendation**: Expand `.env.example` to include all documented app env vars from README with commented-out examples.
- **Principle**: User Promise First

### [14] SPEC keyboard shortcut `Cmd/Ctrl+F` for in-transcript search is not implemented
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§21` vs `frontend/src/routes/memos/[memoId]/+page.svelte`
- **Evidence**:
  - *Doc Claim*: SPEC §21 lists `Cmd/Ctrl+F` for "search inside current transcript"
  - *Code Reality*: The in-transcript search is accessed via a UI button only. No keyboard handler for `Cmd/Ctrl+F` exists in the editor.
- **Impact**: Users expecting `Cmd/Ctrl+F` to open transcript search will be confused.
- **Recommendation**: Implement `Cmd/Ctrl+F` in TranscriptPane or remove from SPEC §21.
- **Principle**: User Promise First

### [15] SPEC hover highlight between waveform and transcript is not implemented
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§18` vs `frontend/src/lib/components/WaveformPane.svelte`
- **Evidence**:
  - *Doc Claim*: SPEC §18: "Hovering waveform segments highlights transcript rows and vice versa"
  - *Code Reality*: The WaveformPane and TranscriptPane pass click-to-seek callbacks but there is no bidirectional hover highlight implementation.
- **Impact**: Missing UX feature described in the spec.
- **Recommendation**: Either implement hover highlighting or remove from SPEC §18.
- **Principle**: User Promise First

### [16] `docker-compose.yml` sets `NANOSCRIBE_OFFLINE=1` and `HF_HUB_OFFLINE=1` in dev by default
- **Severity**: P2 (Minor)
- **Location**: `docker-compose.yml:19-20` vs `README.md:§Offline Mode`
- **Evidence**:
  - *Doc Claim*: README says "If you've already downloaded models and want to run without internet: set HF_HUB_OFFLINE=1 and NANOSCRIBE_OFFLINE=1"
  - *Code Reality*: `docker-compose.yml` sets BOTH to `1` by default. New developers running `make dev` will see models failing to download on first run.
- **Impact**: First-time developers get a broken experience; the readiness card says models can't download.
- **Recommendation**: Set `HF_HUB_OFFLINE=0` and `NANOSCRIBE_OFFLINE=0` in `docker-compose.yml` (like `compose.run.yml` does), or prominently document that dev mode requires pre-cached models.
- **Principle**: User Promise First

### [17] SPEC supported input formats differ between intake specification and OpenAI compat endpoint
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§13.1` vs `backend/app/api/openai_compat.py:52`
- **Evidence**:
  - *Doc Claim*: SPEC §13.1 lists 7 input formats: `wav, mp3, m4a, aac, webm, ogg, opus`
  - *Code Reality*: The OpenAI compat endpoint additionally supports `mp4, mpeg, mpga`. The SPEC doesn't document this asymmetry.
- **Impact**: Users uploading via the OpenAI endpoint get broader format support than the web UI.
- **Recommendation**: Note in SPEC §13.1 that the OpenAI compat endpoint supports additional formats.
- **Principle**: Code as Truth

### [18] `compose.run.yml` bot service requires source tree
- **Severity**: P2 (Minor)
- **Location**: `compose.run.yml:54-56` vs README description
- **Evidence**:
  - *Doc Claim*: README describes `compose.run.yml` as the "end-user runtime compose file" that uses prebuilt images with "No source tree, no bind mounts on code"
  - *Code Reality*: The bot service uses `build: context: ./bot` — requiring the `bot/` directory to be present locally. This contradicts the stated goal.
- **Impact**: End users who download only `compose.run.yml` can't start the bot without cloning the repo.
- **Recommendation**: Either publish a bot image to GHCR or document that `compose.run.yml` requires the `bot/` directory.
- **Principle**: User Promise First

### [19] SPEC §15 API Contract missing two documented, implemented endpoints
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§15.5` vs `README.md:§API Overview`
- **Evidence**:
  - *Doc Claim*: SPEC §15.5 Processing Endpoints lists retry, reprocess, job detail, cancel, SSE events
  - *Code Reality*: README additionally documents `GET /api/memos/{id}/jobs` and `POST /api/memos/{id}/regenerate-diarization`. Both exist in code (`jobs.py:42-47` and `speakers.py:56-67`).
- **Impact**: The SPEC is missing two implemented endpoints.
- **Recommendation**: Add both endpoints to SPEC §15 Processing Endpoints.
- **Principle**: Code as Truth

### [20] `make check` fails unhelpfully if Docker container isn't running
- **Severity**: P2 (Minor)
- **Location**: `Makefile:24-30`
- **Evidence**:
  - *Doc Claim*: README says "Full local verification suite (Docker-backed): make check"
  - *Code Reality*: `make check` calls `docker compose exec funasr ...`. If the container isn't running, this fails with a cryptic Docker error.
- **Impact**: First-time developers running `make check` before `make dev` get an unhelpful error message.
- **Recommendation**: Add a pre-check in `make check` to verify the container is running, with a clear error message directing users to run `make dev` first.
- **Principle**: User Promise First

### [21] VTT export available in OpenAI compat endpoint but not in memo export API
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§15.7` vs `backend/app/api/openai_compat.py:53`
- **Evidence**:
  - *Doc Claim*: SPEC §15.7 Export Endpoints: `GET /api/memos/{memo_id}/export?format=txt|json|srt`
  - *Code Reality*: The memo export API supports `txt`, `json`, `srt`. The OpenAI compat `/v1/audio/transcriptions` endpoint also supports `vtt`. Neither SPEC nor README document VTT availability.
- **Impact**: Users who need WebVTT can only get it through the OpenAI compat endpoint, not through memo export.
- **Recommendation**: Either add VTT to the memo export API, or document the asymmetry.
- **Principle**: User Promise First

### [22] CAM++ / diarization model ID mismatch between docs and code
- **Severity**: P2 (Minor)
- **Location**: `README.md:§Models` vs `backend/app/services/capabilities.py:98`
- **Evidence**:
  - *Doc Claim*: README Models table shows CAM++ model ID as `iic/speech_campplus_sv_zh_en_16k-common_advanced`
  - *Code Reality*: The diarization service uses 3D-Speaker from `/opt/3D-Speaker` (cloned at Docker build time), not a standalone ModelScope model. The ModelScope model ID in the README may not be the actual model used for speaker embedding.
- **Impact**: Users trying to verify model cache state will check for the wrong path.
- **Recommendation**: Verify the actual embedding model used by 3D-Speaker and update the README Models table accordingly.
- **Principle**: Code as Truth (Needs Evidence)

### [23] SPEC typography spec says "Satoshi or Inter" — code uses Inter + Playfair Display
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§22.2` vs `frontend/src/app.html:12-14`
- **Evidence**:
  - *Doc Claim*: SPEC §22.2 "Preferred font: Satoshi or Inter."
  - *Code Reality*: `app.html` loads both Inter (sans-serif) AND Playfair Display (serif). The frontend uses Playfair Display for headings (`font-serif`), giving the app a luxury editorial feel not described in the spec.
- **Impact**: Design spec doesn't reflect the actual serif/sans-serif typography system in use.
- **Recommendation**: Update SPEC §22.2 to document the dual-font system (Inter + Playfair Display).
- **Principle**: Code as Truth

### [24] SPEC says frontend dev server with HMR runs in dev container — SPA is served statically
- **Severity**: P2 (Minor)
- **Location**: `SPEC.md:§31.5` vs `docker-compose.yml`
- **Evidence**:
  - *Doc Claim*: SPEC §31.5 "In development, the frontend should run its dev server and HMR inside the container."
  - *Code Reality*: The funasr service command in `docker-compose.yml` is `["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]`. The frontend is built as a static SPA and served by FastAPI. There is no SvelteKit dev server with HMR running in the container.
- **Impact**: Developers expecting frontend HMR will be confused.
- **Recommendation**: Either add a frontend dev server to the dev compose configuration, or update SPEC §31.5 to reflect the current static-build workflow.
- **Principle**: Code as Truth

---

## P3 — Nit

### [25] SPEC §8 shows `static/` under frontend but directory doesn't exist
- **Severity**: P3 (Nit)
- **Location**: `SPEC.md:§8` vs `frontend/src/`
- **Evidence**:
  - *Doc Claim*: SPEC §8 shows `frontend/static/` as a top-level directory
  - *Code Reality*: No `frontend/static/` directory exists. SvelteKit serves static assets from `src/` during build.
- **Impact**: Developers may create a `static/` directory expecting it to be served.
- **Recommendation**: Remove `static/` from SPEC §8 or note it as a SvelteKit convention.
- **Principle**: Code as Truth

### [26] SPEC §15.2 upload endpoint `files[]` parameter not explained
- **Severity**: P3 (Nit)
- **Location**: `SPEC.md:§15.2` vs `backend/app/api/memos.py:21`
- **Evidence**:
  - *Doc Claim*: SPEC says `files[]` as a request field
  - *Code Reality*: The FastAPI parameter is `files: list[UploadFile] = File(..., alias="files[]")`. The `[]` bracket notation is a FastAPI alias for multipart batch uploads.
- **Impact**: Developers unfamiliar with FastAPI multipart aliases may be momentarily confused.
- **Recommendation**: Add a brief note explaining the bracket notation for multipart batch uploads.
- **Principle**: Code as Truth

### [27] SPEC §31.4 `make check` includes format check but spec doesn't list it
- **Severity**: P3 (Nit)
- **Location**: `SPEC.md:§31.4` vs `Makefile:24-27`
- **Evidence**:
  - *Doc Claim*: SPEC §31.4: "`make check` should run at least: ruff check, ty check, pnpm check, pnpm format:check"
  - *Code Reality*: `make check` additionally runs `ruff format --check` via `backend-check`. The implementation is more strict than the spec — a good thing.
- **Impact**: None — format checking is stricter than required.
- **Recommendation**: Update SPEC §31.4 to include `ruff format --check`.
- **Principle**: Code as Truth

### [28] SPEC §11 data model field types not specified
- **Severity**: P3 (Nit)
- **Location**: `SPEC.md:§11` vs `backend/app/db/migrations/001_initial_schema.sql`
- **Evidence**:
  - *Doc Claim*: SPEC §11 lists data model fields in prose without types
  - *Code Reality*: DB migration defines precise SQL types (e.g., `INTEGER NOT NULL DEFAULT 0` for `transcript_revision`, `TEXT` for text fields, `REAL` for `duration_ms`)
- **Impact**: Minor — developers must read the SQL migrations to know field types.
- **Recommendation**: Add types to SPEC §11 data model definitions (e.g., `transcript_revision: INTEGER, default 0`).
- **Principle**: Code as Truth

### [29] `pnpm-workspace.yaml` exists but is not reflected in SPEC repository structure
- **Severity**: P3 (Nit)
- **Location**: `frontend/pnpm-workspace.yaml` (untracked) vs `SPEC.md:§8`
- **Evidence**:
  - *Doc Claim*: SPEC §8 Repository Target Structure lists frontend files but not `pnpm-workspace.yaml`
  - *Code Reality*: A new untracked `frontend/pnpm-workspace.yaml` file exists (for pnpm build-script approvals). The README project structure documents it, but SPEC §8 does not.
- **Impact**: Minor — only affects SPEC completeness.
- **Recommendation**: Add `pnpm-workspace.yaml` to SPEC §8 frontend file listing, or remove if temporary.
- **Principle**: Code as Truth

---

## Needs Evidence

### [30] README `v0.1.0` release tag status unverified
- **Severity**: Needs Evidence
- **Location**: `README.md:§Quick Reference`
- **Evidence**:
  - *Doc Claim*: `v0.1.0` is tagged as "First stable release (recommended)"
  - *Code Reality*: The version `0.1.0` appears in `backend/pyproject.toml` and `backend/app/main.py`. The publish workflow pushes `:latest` and `:v0.1.0` image tags. Whether a corresponding Git tag or GitHub Release exists could not be verified in this audit.
- **Impact**: Users pulling `v0.1.0` may get an image that doesn't match expectations if the tag is misaligned.
- **Recommendation**: Verify git tag and GitHub release exist and are in sync. Document the tagging strategy.
- **Principle**: User Promise First

### [31] Bot Dockerfile vs main Dockerfile Python version mismatch
- **Severity**: Needs Evidence
- **Location**: `bot/Dockerfile:2` vs `Dockerfile` (multi-stage)
- **Evidence**:
  - *Doc Claim*: (None — code-only observation)
  - *Code Reality*: Bot Dockerfile uses `python:3.13-alpine` as builder and runtime. The main Dockerfile uses `python:3.12-bookworm` for the backend build stage. This is a version mismatch between services running in the same compose stack.
- **Impact**: Minor — different Python versions in different containers is normal, but worth noting for dependency compatibility awareness.
- **Recommendation**: Document the Python version split or align both to the same version.
- **Principle**: Code as Truth

---

## Summary of All Findings

| # | Severity | Area | Title |
|---|----------|------|-------|
| 01 | P0 | Docker | HEALTHCHECK targets `/health` but endpoint is `/api/system/health` |
| 02 | P1 | SPEC/Code | `streaming_partial_transcript` documented but not implemented |
| 03 | P1 | SPEC | `tailwind.config.ts` in spec but file doesn't exist |
| 04 | P1 | SPEC | `workers/` directory in spec but code uses `services/worker.py` |
| 05 | P1 | README | VAD/chunking/warm-model/timeout env vars not documented |
| 06 | P2 | SPEC/Frontend | Accent color `#00d4ff` in spec but `#D4AF37` in frontend |
| 07 | P2 | SPEC/README | `diarization.json` in storage layout but DB-backed |
| 08 | P1 | Frontend | Settings stored locally but never sent to API |
| 09 | P1 | CI/README | CI skips GPU tests without documentation |
| 10 | P2 | Docker | Bot unnecessarily mounts telegram-api-data volume |
| 11 | P2 | SPEC | Frontend stores count (6 vs 11) |
| 12 | P2 | SPEC | Backend services list incomplete (8 vs 16) |
| 13 | P2 | Config | .env.example missing app configuration vars |
| 14 | P2 | SPEC/Frontend | `Cmd/Ctrl+F` keyboard shortcut not implemented |
| 15 | P2 | SPEC/Frontend | Hover highlighting between waveform and transcript not implemented |
| 16 | P2 | Config | Dev docker-compose sets offline=1 preventing first-run model download |
| 17 | P2 | SPEC/Code | Supported formats differ between intake (7) and OpenAI compat (10+) |
| 18 | P2 | Config | compose.run.yml bot requires source tree |
| 19 | P2 | SPEC | Missing `GET /memos/{id}/jobs` and `POST /regenerate-diarization` endpoints |
| 20 | P2 | Makefile | `make check` fails unhelpfully if container not running |
| 21 | P2 | SPEC/Code | VTT export in OpenAI compat but not memo export API |
| 22 | P2 | README/Code | CAM++ model ID difference — needs evidence |
| 23 | P2 | SPEC/Frontend | Typography "Satoshi or Inter" vs actual Inter + Playfair Display |
| 24 | P2 | SPEC/Docker | Spec says frontend dev server with HMR; SPA served statically |
| 25 | P3 | SPEC | `static/` directory in spec tree but doesn't exist |
| 26 | P3 | SPEC | `files[]` parameter not explained in detail |
| 27 | P3 | SPEC | `make check` format check more comprehensive than spec |
| 28 | P3 | SPEC | Data model field types not specified |
| 29 | P3 | SPEC | `pnpm-workspace.yaml` not in SPEC structure |
| 30 | NE | README/Git | `v0.1.0` release tag — needs verification |
| 31 | NE | Docker/Bot | Python version mismatch between bot and main containers |

---

## Side Effects

- If screenshots are updated to reflect the gold accent color (#D4AF37), the README screenshots will need regeneration.
- If SPEC storage layout is corrected for `diarization.json`, verify README storage layout for consistency.
- The deleted `TASKS/` directory removed the original bot integration spec — bot documentation now lives only in README.
