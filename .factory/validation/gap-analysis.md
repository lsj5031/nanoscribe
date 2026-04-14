# Spec Gap Analysis

**Date:** 2026-04-14
**Branch:** main

## Summary

| Status      | Count |
|-------------|-------|
| Closed      | 6     |
| Still open  | 8     |
| **Total**   | 14    |

---

## All Gaps

| #  | Area     | Gap                                                        | Severity | Status     |
|----|----------|------------------------------------------------------------|----------|------------|
| 1  | Backend  | `streaming_partial_transcript` missing from capability manifest | Low      | Open       |
| 2  | Backend  | Worker in `services/` instead of `workers/` directory      | Cosmetic | Open       |
| 3  | Backend  | `ty check` may not run cleanly                             | Medium   | Open       |
| 4  | Frontend | Export/Copy/Re-run buttons are stubs in editor              | High     | **Closed** |
| 5  | Frontend | In-editor transcript search not implemented                 | High     | **Closed** |
| 6  | Frontend | Waveform zoom controls missing                             | Medium   | **Closed** |
| 7  | Frontend | Shift+Arrow 15s seek not implemented                       | Low      | **Closed** |
| 8  | Frontend | Global search may not work well from editor context        | Low      | Open       |
| 9  | Frontend | No partial transcript SSE consumption                      | Low      | Open       |
| 10 | Frontend | No bidirectional waveform/transcript hover highlight        | Medium   | **Closed** |
| 11 | Frontend | No PWA install prompt in UI                                | Low      | Open       |
| 12 | Frontend | No tablet responsive layout                                | Low      | Open       |
| 13 | Infra    | No CI configuration                                        | Medium   | **Closed** |
| 14 | Infra    | No `tailwind.config.ts` (using Tailwind v4 `@theme`)       | Cosmetic | Open       |

---

## Closed Gaps

### #4 — Export/Copy/Re-run buttons (was: stubs)
- **ExportMenu.svelte** opens `/api/memos/{id}/export?format=` directly (TXT, JSON, SRT).
- **Copy** uses `navigator.clipboard.writeText(getFullTranscriptText())` with "Copied!" feedback.
- **Re-run transcription** calls `POST /api/memos/{id}/reprocess` with SSE reconnect.
- **Re-run diarization** calls `POST /api/memos/{id}/regenerate-diarization` with SSE reconnect.

### #5 — In-editor transcript search
- **TranscriptPane.svelte** has full search bar with query input, match count (N/M), prev/next navigation, text highlighting, auto-scroll to match.
- Toggle via Cmd/Ctrl+F (KeyboardShortcuts.svelte) or search icon button.
- Escape closes search. Enter/Shift+Enter cycles matches.

### #6 — Waveform zoom controls
- **WaveformPane.svelte** has zoom in/out buttons with persisted zoom level (1x–8x).
- Uses WaveSurfer.js `zoom()` API. Level saved to localStorage.

### #7 — Shift+Arrow 15s seek
- ArrowLeft/Right handlers in `+page.svelte` use `e.shiftKey ? 15000 : 5000` delta.

### #10 — Bidirectional waveform/transcript hover highlight
- WaveSurfer `hover` event maps cursor position to segment index via `setHoveredSegmentIndex()`.
- TranscriptPane `onmouseenter/leave` on each segment row sets the same index.
- Both WaveformPane and TranscriptPane read `hoveredIndex` and apply highlight styling.

### #13 — CI configuration
- `.github/workflows/check.yml` runs on push/PR to main: builds dev image, starts container, runs backend-check and frontend-check.

---

## Remaining Open Gaps

### #1 — `streaming_partial_transcript` (Low)
- FunASR batch mode does not emit partial transcripts. The capability manifest in `capabilities.py` omits `streaming_partial_transcript`. No backend or frontend support exists. Low priority until FunASR supports streaming mode.

### #2 — Worker directory structure (Cosmetic)
- Worker lives in `backend/app/services/worker.py` instead of the spec-target `backend/app/workers/`. No functional impact.

### #3 — `ty check` may not run cleanly (Medium)
- `pyproject.toml` has `[tool.ty]` config. `ty` is a relatively new/unstable type checker. Needs manual verification that `make backend-check` passes cleanly.

### #8 — Global search from editor context (Low)
- Cmd+K search overlay is mounted globally in the layout. It should work from the editor page, but the SearchOverlay component was not specifically tested in the editor context.

### #9 — No partial transcript SSE consumption (Low)
- Tied to gap #1. No backend `transcript.partial` events are emitted. Frontend ProcessingOverlay only handles stage/progress events.

### #11 — No PWA install prompt in UI (Low)
- PWA manifest and service worker are configured via `vite-plugin-pwa`. No custom `beforeinstallprompt` handling or install button in TopBar.

### #12 — No tablet responsive layout (Low)
- Library has responsive grid (`sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`). Editor page has no responsive breakpoints — the two-pane layout is fixed on all screen sizes.

### #14 — No `tailwind.config.ts` (Cosmetic)
- Using Tailwind v4 with `@theme` directives in `app.css`. This is the correct v4 approach; the spec listed a v3-era config file.
