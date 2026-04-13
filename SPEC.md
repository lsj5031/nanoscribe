## NanoScribe Product And Engineering Spec

### Document Status

- Status: Draft for implementation
- Product name: NanoScribe
- Scope: Lean, UX-first local app for FunASR
- Deployment target: Single Docker image, local-only, GPU-enabled when available

## 1. Product Summary

NanoScribe is a polished local web app for FunASR that makes voice memo transcription feel fast, premium, and dependable without turning the project into a larger platform than it needs to be.

The product goal is simple: drop or record audio, watch progress in real time, open a clean transcript editor, fix what matters, and export useful results. The app should feel like a great interface for FunASR, not a separate AI product stack built beside it.

## 2. Product Principles

- UX over feature count.
- Toolkit-first: use FunASR-native capabilities instead of rebuilding them in app code.
- Local-first: all audio, transcripts, and metadata stay on the machine.
- Editor-first: the main value is getting from audio to an editable transcript quickly.
- Prefer one supported happy path: choose a recommended FunASR preset and avoid designing the product around many fallback combinations.
- Recoverable state: refreshes, browser restarts, and backend restarts should not strand jobs or lose edits.

## 3. What This Release Includes

### 3.1 Core Transcription Flow

- Single-file upload.
- Batch upload.
- Drag-and-drop anywhere in the app.
- In-app microphone recording.
- Real-time job progress via SSE.
- Timestamped transcript output.
- Speaker diarization when supported by the active FunASR configuration.
- Partial transcript streaming when supported by the active FunASR configuration.
- Manual transcript editing with autosave.
- Clickable timestamps and synchronized audio playback.

### 3.2 Library And Navigation

- Library home screen.
- Search across memo titles and transcript text.
- Grid and list views.
- Sort by recent and duration.
- Filter by status and language.
- Memo cards with title, duration, last edited, speaker count, and waveform preview.
- Failed-job retry from the library.

### 3.3 Transcript Editor

- Interactive waveform.
- Resizable transcript layout.
- Playback transport and speed control.
- Search inside transcript.
- Speaker rename per memo.
- Color-coded speaker segments.
- Copy transcript.
- Re-run transcription.
- Re-run diarization when supported.

### 3.4 Export

- TXT export.
- JSON export.
- SRT export.

### 3.5 Settings And Readiness

- Active model and device status.
- Language auto-detect with manual override.
- Diarization on or off.
- Hotwords input.
- Cache and model readiness status.
- Supported runtime requirements.

### 3.6 Platform UX

- Dark mode default.
- Keyboard-first controls.
- PWA installability.
- Responsive review experience on tablet-sized screens.

## 4. Explicitly Out Of Scope

The following are intentionally not part of this release:

- Cross-memo speaker memory.
- ChromaDB or vector search.
- Local summaries or key points.
- Segment comments or notes.
- Version history.
- PDF export.
- HTML share export.
- Remote sharing.
- Multi-user accounts.
- Cloud sync.
- Telemetry.

These are not missing features. They are deliberate scope cuts to keep the app centered on excellent FunASR UX.

## 5. FunASR Responsibilities Vs App Responsibilities

### 5.1 FunASR Responsibilities

NanoScribe should lean on FunASR for:

- Speech recognition.
- VAD segmentation.
- Timestamp generation.
- Punctuation restoration.
- Hotword-aware recognition.
- Speaker diarization when supported by the chosen model path.
- Streaming or low-latency output when supported by the chosen mode.

### 5.1.1 Recommended Packaged Preset

The product should ship around one recommended backend preset rather than exposing arbitrary model composition.

Initial supported preset:

- ASR model: `FunAudioLLM/Fun-ASR-Nano-2512`
- VAD model: `fsmn-vad`
- Punctuation model: `ct-punc`
- Timestamps: enabled
- Hotwords: enabled
- Diarization: exposed only if the packaged backend preset includes a validated FunASR speaker pipeline for this release

Users may control language, hotwords, and whether diarization is requested when supported, but they should not be asked to assemble low-level FunASR model combinations in the product UI.

### 5.2 NanoScribe Responsibilities

NanoScribe is responsible for:

- File intake and recording UX.
- Job queueing, progress, cancellation, and retry.
- Audio normalization and waveform extraction.
- Transcript persistence and editing.
- Playback and transcript synchronization.
- Memo-local speaker labels and colors.
- Library browsing and text search.
- Export packaging.
- Settings, model readiness, and supported-runtime messaging.

### 5.3 Capability Rule

The backend must expose a runtime capability manifest. The frontend should use that manifest to support one recommended preset cleanly, and hide or omit controls that are not supported by the active runtime rather than building elaborate fallback UX for every combination.

## 6. Runtime Architecture

### 6.1 Deployment Topology

The application runs as one local web app origin in one Docker image.

- FastAPI is the only runtime server.
- SvelteKit is built as a static SPA and served by FastAPI.
- API routes live under `/api`.
- SSE streams are served by FastAPI.
- One in-process worker handles transcription jobs.
- GPU is used when available.

### 6.1.1 Supported Runtime Profile

The supported runtime profile for this release is:

- Local Docker deployment
- NVIDIA Container Toolkit installed
- One accessible NVIDIA GPU
- Mounted Hugging Face and ModelScope caches
- Local bind-mounted `/app/data` persistence

This is the runtime profile the product UX, validation, and acceptance criteria are designed around.

CPU-only execution may be detectable for diagnostics, but it is not the primary supported runtime for this release and should not drive product design decisions.

### 6.2 Required Runtime Components

- FastAPI.
- Uvicorn.
- FunASR and model dependencies.
- ffmpeg.
- SQLite.
- Local filesystem storage under `/app/data`.
- SvelteKit frontend build output.

### 6.3 Process Model

- One API process.
- One transcription worker loop.
- One queued GPU job at a time.
- Derived work like waveform extraction and export generation may run inline or in a lightweight secondary lane, but must not complicate deployment.

## 7. First-Run And Readiness UX

This is required scope because local model-backed apps feel broken without it.

### 7.1 First Launch

- The app shows a readiness card if models are not yet available.
- The user sees whether the backend is downloading models, warming them up, or waiting for configuration.
- If the machine is offline and models are missing, the UI explains exactly why transcription is unavailable.

### 7.2 Ready State

- The home screen shows whether the app is ready to transcribe.
- Device status is visible.
- Active model preset is visible.

### 7.3 Supported Runtime Rules

- NanoScribe should ship with one recommended FunASR preset that defines the primary product experience.
- The core UX should be designed around that preset, not around a matrix of optional runtime combinations.
- If a capability is unavailable for the active runtime, the UI should hide the related control or clearly mark it unavailable in settings.
- If the runtime does not meet the supported profile needed for the primary experience, the app should say so directly during setup or readiness instead of pretending the experience is equivalent.

### 7.4 Supported Browsers

- Primary supported browsers: current desktop Chrome and Edge.
- Secondary support: current desktop Firefox for upload, playback, and transcript editing.
- Recording UX and PWA install behavior should be validated against Chromium browsers first.

## 8. Repository Target Structure

The current repo is only the Docker foundation. The implementation target structure should become:

```text
/
  frontend/
    src/
    static/
    package.json
    svelte.config.js
    vite.config.ts
    tailwind.config.ts
  backend/
    app/
      api/
      core/
      db/
      services/
      workers/
      schemas/
      main.py
    pyproject.toml
  data/
  Dockerfile
  docker-compose.yml
  Makefile
  SPEC.md
```

## 9. Storage Layout

All persistent data lives under the mounted data directory.

```text
/app/data/
  nanoscribe.db
  memos/
    <memo_id>/
      source.original
      normalized.wav
      waveform.json
      transcript.raw.json
      transcript.final.json
      diarization.json
      exports/
        transcript.txt
        transcript.json
        transcript.srt
```

## 10. Source Of Truth Rules

- SQLite is the source of truth for memo metadata, jobs, current transcript segments, and memo-local speaker labels.
- Filesystem artifacts store source audio, normalized audio, waveform data, raw backend outputs, and exports.
- No vector database is part of the release.

## 11. Data Model

### 11.1 `memos`

- `id`
- `title`
- `source_kind`
- `source_filename`
- `duration_ms`
- `language_detected`
- `language_override`
- `status`
- `speaker_count`
- `transcript_revision`
- `created_at`
- `updated_at`
- `last_opened_at`
- `last_edited_at`

### 11.2 `jobs`

- `id`
- `memo_id`
- `job_type`
- `status`
- `stage`
- `progress`
- `eta_seconds`
- `device_used`
- `error_code`
- `error_message`
- `attempt_count`
- `created_at`
- `started_at`
- `finished_at`

### 11.3 `segments`

- `id`
- `memo_id`
- `ordinal`
- `start_ms`
- `end_ms`
- `text`
- `speaker_key`
- `confidence`
- `edited`
- `created_at`
- `updated_at`

### 11.4 `memo_speakers`

- `id`
- `memo_id`
- `speaker_key`
- `display_name`
- `color`
- `created_at`
- `updated_at`

## 12. Capability Manifest

The backend must expose at least:

- `ready`
- `gpu`
- `device`
- `asr_model`
- `vad`
- `timestamps`
- `speaker_diarization`
- `streaming_partial_transcript`
- `hotwords`
- `language_auto_detect`
- `recording`

The frontend uses this manifest to drive the supported UI surface for the active runtime.

## 13. Processing Pipeline

### 13.1 Intake

Supported inputs:

- `wav`
- `mp3`
- `m4a`
- `aac`
- `webm`
- `ogg`
- `opus`

Flow:

1. User uploads files or submits a browser recording.
2. Backend creates memo rows and queued jobs immediately.
3. Original files are stored under the memo directory.
4. ffmpeg normalizes audio to a canonical WAV format.
5. Duration and waveform peaks are extracted.

### 13.2 Recognition

1. Determine active recognition configuration from settings and capabilities.
2. Run FunASR recognition with timestamps enabled.
3. Enable VAD and punctuation through FunASR-native configuration.
4. Apply hotwords when configured.
5. Run diarization when enabled and supported.
6. Merge ASR output and diarization output into transcript segments.
7. Persist raw outputs and editor-ready transcript data.

### 13.3 Post-Processing

1. Store transcript segments.
2. Build memo-local speaker labels.
3. Generate exports on demand or after completion.

## 14. Job Lifecycle

### 14.1 Job States

- `queued`
- `preprocessing`
- `transcribing`
- `diarizing`
- `finalizing`
- `completed`
- `failed`
- `cancelled`

### 14.2 Recovery Rules

- On startup, stale active jobs are requeued or marked failed with clear metadata.
- Refreshing the page must not lose track of a running job.
- Failed jobs can be retried from the library.
- Cancelling a running job is best effort and must leave the memo in a readable state.

## 15. API Contract

### 15.1 System Endpoints

#### `GET /api/system/capabilities`

Returns runtime feature support, model metadata, and readiness state.

#### `GET /api/system/health`

Returns backend, DB, storage, and model-readiness status.

### 15.2 Memo Endpoints

#### `POST /api/memos`

Multipart upload endpoint for one or more files.

Request fields:

- `files[]`
- `title` optional
- `source_kind`
- `language` optional
- `enable_diarization`
- `hotwords` optional

Response returns created memos and jobs.

#### `GET /api/memos`

Library listing with pagination, search, sort, and filters.

Query params:

- `q`
- `sort`
- `status`
- `language`
- `page`
- `page_size`

#### `GET /api/memos/{memo_id}`

Returns memo metadata, current job summary, export availability, and editor bootstrap state.

Default title rules:

- Uploaded files default to the original filename without extension.
- In-app recordings default to a timestamped title such as `Recording 2026-04-13 10-32`.
- Users can rename memos from the library and editor views.

#### `DELETE /api/memos/{memo_id}`

Deletes memo metadata and local artifacts.

#### `POST /api/memos/{memo_id}/retry`

Retries the last failed job with the current memo settings.

### 15.3 Transcript Endpoints

#### `GET /api/memos/{memo_id}/segments`

Returns ordered transcript segments and the current revision number.

#### `PATCH /api/memos/{memo_id}/segments`

Updates transcript segment text and speaker labels.

Request body includes:

- `base_revision`
- `updates[]`

If the revision is stale, return `409` with the latest transcript payload.

### 15.4 Speaker Endpoints

#### `GET /api/memos/{memo_id}/speakers`

Returns memo-local speakers.

#### `PATCH /api/memos/{memo_id}/speakers`

Updates memo-local speaker names and colors.

### 15.5 Processing Endpoints

#### `POST /api/memos/{memo_id}/reprocess`

Creates a new transcription job using current settings.

#### `POST /api/memos/{memo_id}/regenerate-diarization`

Creates a diarization-only job when supported.

#### `GET /api/jobs/{job_id}`

Returns current job snapshot.

#### `POST /api/jobs/{job_id}/cancel`

Requests cancellation.

#### `GET /api/jobs/{job_id}/events`

Server-Sent Events stream.

Supported event types:

- `job.stage`
- `job.progress`
- `waveform.ready`
- `transcript.partial`
- `job.warning`
- `job.completed`
- `job.failed`
- `job.cancelled`

Reconnect behavior:

- On page load or reconnect, the client first fetches the latest memo or job snapshot.
- The client then opens a fresh SSE connection for live updates.
- V1 does not require resumable event streams or event replay.

### 15.6 Search Endpoint

#### `GET /api/search`

Searches memo titles and transcript text.

### 15.7 Export Endpoints

#### `GET /api/memos/{memo_id}/export?format=txt|json|srt`

Returns or generates the requested export.

## 16. Frontend Information Architecture

### 16.1 Routes

- `/`
- `/memos/[memoId]`
- `/settings`

### 16.2 App Shell

- Persistent top bar.
- Global search entry point.
- Settings access.
- Active job indicator.
- Install prompt integration.

## 17. Detailed Screen Specification

### 17.1 Home And Library Screen

#### Top Bar

- Logo and wordmark.
- Global search field.
- Active jobs indicator.
- Settings button.

#### Empty State

- Full-screen drop zone.
- Decorative animated waveform.
- Primary text: drop voice memo here.
- Secondary text: processed locally with FunASR.
- Record CTA.
- Readiness card if models are not ready.

#### Populated State

- Floating upload action.
- Grid or list toggle.
- Sort and filter controls.
- Search updates instantly.
- Cards show waveform thumbnail, title, duration, speaker count, last edited, and processing status.
- Failed cards expose retry.

### 17.2 Recording Flow

- Open recording modal or sheet.
- Request microphone permission clearly.
- Handle denied permission with an actionable message.
- Show input level visualization.
- Show recording duration.
- Allow pause, resume, discard, and submit.
- Allow input-device selection if the browser exposes it.
- Keep recording preview local before upload.

### 17.3 Processing Overlay

- Stage-based progress ring.
- Estimated remaining time when available.
- Waveform preview once ready.
- Partial transcript stream when supported.
- Background action returning the user to the library.
- Cancel action.
- Toast on completion or failure.

### 17.4 Transcript Editor

#### Layout

- Left pane about 70 percent width by default.
- Right pane about 30 percent width by default.
- User-resizable split.

#### Left Pane

- Audio transport controls.
- Playback speed selector.
- Main waveform.
- Speaker segment band over waveform.
- Zoom controls.
- Current playhead.
- Click and keyboard seek.

#### Right Pane

- Search-in-transcript control.
- Segment list.
- Speaker badges.
- Editable segment text.
- Current segment highlight during playback.

#### Floating Toolbar

- Play or pause.
- Speed.
- Export menu.
- Copy transcript.
- Re-run diarization when supported.
- Re-run transcription.

#### Speaker Editing

- Each memo starts with local speaker labels such as `Speaker 1`.
- User can rename local speakers in place.
- Speaker colors remain consistent within the memo.

## 18. Editor Behavior Rules

- Transcript edits autosave on debounce.
- Each successful autosave increments the current revision.
- Reprocessing must never silently overwrite user edits.
- If a stale client writes using an old revision, backend returns `409` and the latest state.
- Clicking a timestamp seeks audio and updates selected segment.
- Hovering waveform segments highlights transcript rows and vice versa.

## 19. Search Specification

- Global search covers memo title and transcript text.
- Search results return memo, segment preview, and timestamp when available.
- Search should be implemented with straightforward local indexing, preferably SQLite FTS, without adding a separate search system.

## 20. Settings Specification

- Show current backend readiness.
- Show current model name.
- Show device in use.
- Toggle diarization by default.
- Set language to auto or specific language.
- Enter hotwords.
- Show cache location summary.
- Show basic storage, runtime requirements, and troubleshooting information.

## 21. Keyboard Specification

- `Space` play or pause.
- `Cmd/Ctrl+K` global search.
- `Cmd/Ctrl+F` search inside current transcript.
- `Left` and `Right` seek 5 seconds.
- `Shift+Left` and `Shift+Right` seek 15 seconds.
- `Up` and `Down` move selected segment.
- `Enter` focus selected segment editor.
- `Esc` close active modal or search surface.

## 22. Design System Specification

### 22.1 Visual Direction

- Dark mode default.
- Strong teal primary accent `#00d4ff`.
- Speaker colors generated as soft, readable pastels.
- Glass and blur used sparingly.
- Dense, crisp editor layout.

### 22.2 Typography

- Preferred font: Satoshi or Inter.
- Transcript text must prioritize readability over branding flair.

### 22.3 Motion

- Smooth, restrained transitions.
- Waveform breathing on load.
- Segment highlight pulse.
- Progress ring interpolation.
- Motion must support clarity, not distract from editing.

## 23. Accessibility Specification

- WCAG AA contrast.
- Full keyboard navigation.
- Clear focus states.
- ARIA labels on transport controls and recording controls.
- Screen-reader friendly timestamps.
- No feature required for core use may depend only on pointer interaction.

## 24. Frontend State Model

### 24.1 Stores

- `capabilitiesStore`
- `libraryStore`
- `jobStore`
- `recordingStore`
- `editorStore`
- `settingsStore`

### 24.2 Persistence

- UI preferences persist locally.
- Editor pane size persists locally.
- Active jobs rehydrate from backend on reload.

## 25. Backend Services

- Intake service.
- Audio normalization service.
- Waveform extraction service.
- FunASR transcription service.
- Diarization merge service.
- Transcript persistence service.
- Search service.
- Export service.

Services should stay small and direct. No speculative abstraction layers are required.

## 26. Error Handling Rules

- Unsupported format returns a clear import error.
- Corrupt media returns a clear import error.
- Diarization failure degrades to transcript without speaker separation when possible.
- Export failure in one format must not break the memo.
- Missing model readiness must produce a clear first-run or offline message.
- Microphone permission denial must have an obvious recovery path.
- Unsupported runtime combinations should be identified early in setup rather than discovered mid-flow.

## 27. Performance Targets

- UI acknowledges upload or recording submission in under 200 ms.
- Processing screen appears immediately after job creation.
- Waveform preview appears as early as practical after normalization.
- Transcript editor loads in under 1 second for typical completed memos.
- Search feels instant for a normal single-user library.

## 28. Security And Privacy Requirements

- No cloud dependency for core flows after model download.
- No telemetry.
- No transcript content leaves the local environment.
- All files remain under the mounted app data directory unless explicitly exported.

## 29. Acceptance Criteria

- A single Docker deployment starts one local web app origin serving frontend and backend.
- Users can upload supported audio formats and submit in-app recordings.
- The app clearly shows first-run readiness and model availability.
- The app clearly identifies whether the local machine matches the supported runtime profile.
- Batch upload creates separate memos and jobs with independent progress.
- SSE streams expose real-time job progress and stage updates.
- Partial transcript updates are shown when the active mode supports them.
- Completed transcripts include timestamps.
- Diarization is shown when supported and explained when unavailable.
- The transcript editor supports autosave, click-to-seek, speaker rename, and transcript search.
- Reprocessing and diarization regeneration are available from the editor when supported.
- Library search works across titles and transcript text.
- Failed jobs can be retried from the library.
- Export works for TXT, JSON, and SRT.
- Refreshing or restarting the app does not orphan active jobs or lose saved edits.
- The app clearly communicates its supported runtime profile before a user starts transcription.
- The app is installable as a PWA and works well on desktop-class browsers.

## 30. Future Extensions

These may be added later if the core product is excellent and stable:

- Cross-memo speaker memory.
- Semantic search.
- Local summaries.
- Version history.
- Rich comments.
- PDF and HTML share export.

## 31. Developer Readiness

Developer readiness is part of the release definition. The repo should be ready for disciplined day-to-day development from the start rather than adding quality gates after the codebase grows.

### 31.1 Backend Tooling

- Backend development and verification must run inside the project Docker environment.
- Python linting and formatting must use Ruff.
- Python type checking must use `ty`.
- Ruff should handle import ordering so no separate isort setup is needed.
- Backend commands should be runnable from the repo root through Docker-backed wrappers.

Required backend commands:

- `ruff format`
- `ruff check`
- `ty check`

### 31.2 Frontend Tooling

- Frontend development and verification must run inside the project Docker environment.
- Frontend package management should use `pnpm`.
- Frontend correctness checks must include `svelte-check`.
- Frontend formatting should use Prettier.
- Frontend scripts should be runnable from the repo root via `make` or root package scripts that execute inside the container.

Required frontend commands:

- `pnpm check` or equivalent wrapper around `svelte-check`
- `pnpm format:check`

### 31.3 Hooks And Local Quality Gates

- A pre-commit hook must be installed from the beginning of the project.
- Pre-commit should run the fast, high-signal checks that catch broken formatting and obvious issues before code lands.
- Hooks should be easy to install with one documented command.

Required pre-commit behavior:

- Run Ruff format or Ruff format check on Python files.
- Run Ruff check on Python files.
- Run Prettier on frontend files or enforce Prettier formatting checks.
- Run lightweight file hygiene checks such as trailing whitespace and end-of-file fixes.

Hook execution rule:

- Pre-commit hooks must call repo-managed Docker-backed commands, not host-installed Python or Node binaries.

### 31.4 Full Verification Command

The repo must have one obvious verification entry point for local development.

Preferred root commands:

- `make check` for the full local verification suite.
- `make backend-check`
- `make frontend-check`
- `make hooks-install`

`make check` should run at least:

- `ruff check`
- `ty check`
- `pnpm check`
- `pnpm format:check`

All of these commands should execute inside Docker so a developer does not need local Python, Node, pnpm, Ruff, or `ty` installed on the host machine.

### 31.5 Container-First Development

- Day-to-day development should happen in the project container, not on the host system.
- The host machine should only need Docker, Docker Compose support, and any GPU container runtime prerequisites.
- Python tooling, Node tooling, pnpm, and app dependencies must live in the containerized dev environment.
- Bind mounts should provide live code editing from the host while execution stays inside the container.
- The repo should provide documented commands for starting the app, running checks, and opening a shell in the dev container.
- In development, the backend should run with reload enabled inside the container.
- In development, the frontend should run its dev server and HMR inside the container.
- In production, the built SvelteKit SPA should be served by FastAPI from the same image.

Preferred root commands:

- `make dev`
- `make shell`
- `make check`
- `make backend-check`
- `make frontend-check`
- `make hooks-install`

### 31.6 CI Parity

- The same checks run locally and in CI.
- CI should not introduce a different validation story than local development.
- If a command is required in CI, it must be documented and runnable locally.

### 31.7 Testing Philosophy

- Do not add broad low-value test suites just to look complete.
- Prefer a small number of high-value tests around transcript persistence, job lifecycle, API contracts, and editor-saving behavior.
- Tooling and checks should stay lightweight enough that they are used constantly.
- Track SQLite schema changes with migrations from day one, using a simple migration workflow rather than manual schema drift.

### 31.8 Acceptance Criteria For Dev Readiness

- The repo includes Ruff configuration.
- The repo includes `ty` configuration.
- The frontend includes a `svelte-check` command.
- The repo includes pre-commit configuration from day one.
- A developer can install hooks and run the full verification suite with documented root commands.
- A developer does not need to install Python, Node, pnpm, Ruff, `ty`, or frontend dependencies on the host machine.

## 32. Implementation Notes For This Repo

The current repo only provides the container baseline. To satisfy this spec, implementation must extend the current scaffolding by:

- Converting the Docker image into a multi-stage build with frontend build assets and backend runtime.
- Adding ffmpeg and backend web dependencies.
- Adding the SvelteKit frontend app.
- Adding the FastAPI backend app.
- Preserving the mounted Hugging Face and ModelScope caches already described in [README.md](file:///home/leo/code/funasr/README.md#L1-L52) and [docker-compose.yml](file:///home/leo/code/funasr/docker-compose.yml#L1-L25).
- Preserving `/app/data` as the primary bind-mounted persistence directory.

## 33. Final Product Positioning

NanoScribe is a high-quality interface for FunASR.

FunASR handles the speech intelligence. NanoScribe makes it feel great to use.
