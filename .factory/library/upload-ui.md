# Upload UI

## Components

### `upload.svelte.ts` (Store)
- Manages upload state: active job, error messages
- `uploadFiles(files)` - validates audio files, calls `POST /api/memos`, tracks progress via SSE
- `cancelUpload()` - calls `POST /api/jobs/{id}/cancel`
- `dismissUpload()` - clears the active upload overlay
- `isAudioFile(file)` - checks if file has supported extension (wav, mp3, m4a, aac, webm, ogg, opus)
- SSE connects to `/api/jobs/{id}/events` and listens for `job.stage`, `job.progress`, `job.completed`, `job.failed`, `job.cancelled` events

### `DropOverlay.svelte` (Component)
- Global drag-and-drop overlay using `svelte:window` events
- Shows a teal-bordered drop zone with upload icon when files are dragged over the app
- Uses `dragCounter` pattern to handle nested dragenter/dragleave events
- Delegates to `uploadFiles()` for actual upload

### `ProcessingOverlay.svelte` (Component)
- Full-screen overlay with SVG progress ring (circular arc)
- Shows memo title, stage label (queued/preprocessing/transcribing/etc.), and progress percentage
- Cancel button for non-terminal states, Dismiss button for terminal states
- Auto-dismisses 1.5s after reaching terminal state (completed/failed/cancelled)
- Progress ring color: teal during processing, green on success, red on failure

### `ErrorToast.svelte` (Component)
- Bottom-center toast with red error icon, error message, and dismiss button
- Auto-dismisses after 6 seconds
- Shows for unsupported file formats, upload failures, etc.

## Integration

- All overlays are mounted in `+layout.svelte` (global scope)
- `DropOverlay` and `ProcessingOverlay` are always present, conditionally visible
- File input button only on home page (`+page.svelte`) within the empty state drop zone
- Drag-and-drop works on all pages (home, library, settings, editor)
- The upload area in empty state is a `<button>` element that opens the file picker
- Hidden `<input type="file">` accepts supported audio formats with `multiple` attribute

## Key Behaviors
- Single file upload: shows processing overlay with SSE progress tracking
- Multiple file upload: uploads all, shows overlay for first file
- Non-audio files: error toast "Unsupported file format..."
- Mixed files: valid ones uploaded, error toast for skipped unsupported files
- Cancel during processing: calls cancel API, shows cancelled state briefly, then dismisses
