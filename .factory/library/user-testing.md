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
