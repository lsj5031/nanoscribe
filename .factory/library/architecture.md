# Architecture

How NanoScribe works — components, relationships, data flows, and invariants.

## Overview

NanoScribe is a single-container local web app for FunASR voice transcription. FastAPI serves a SvelteKit SPA (built as static files) and provides REST API + SSE endpoints. One in-process worker handles transcription jobs sequentially on GPU.

## Components

```
Browser (SvelteKit SPA)
  ↓ REST + SSE
FastAPI Backend
  ├── API Layer (endpoints under /api)
  ├── Services (intake, normalization, waveform, transcription, diarization-merge, export, search)
  ├── Worker Loop (sequential GPU job processor)
  ├── SQLite Database (metadata, jobs, segments, speakers)
  └── Filesystem (audio artifacts under /app/data/memos/)
```

## Data Flow

1. **Upload/Record** → FastAPI receives file → creates memo + job → stores original audio
2. **Worker picks up job** → ffmpeg normalizes → extracts duration + waveform → runs FunASR ASR → runs 3D-Speaker diarization (if enabled) → merges ASR+diarization by timestamp overlap → persists segments → generates exports
3. **Browser** → SSE stream receives progress events → library updates in real-time → editor loads waveform + segments
4. **Edit** → PATCH segments with base_revision → optimistic concurrency → revision increment
5. **Export** → generate TXT/JSON/SRT from current segment state

## Key Models

- **memos**: Audio files with metadata (title, duration, status, speaker_count)
- **jobs**: Processing pipeline state (queued→preprocessing→transcribing→diarizing→finalizing→completed/failed/cancelled)
- **segments**: Timestamped transcript chunks with text, speaker_key, confidence
- **memo_speakers**: Per-memo speaker labels with display names and colors

## Key Invariants

- One GPU job at a time (serialized queue)
- Revision-based optimistic concurrency for transcript edits
- All persistent data under /app/data
- Capability manifest drives frontend UI surface
- Diarization is a separate pass from ASR, merged by timestamp overlap
- Reprocessing never silently overwrites user edits
- SPA catch-all route uses path traversal protection via `pathlib.resolve()` + `relative_to()` to verify served files are within STATIC_DIR

## External Dependencies

- **FunASR** (Fun-ASR-Nano-2512 + fsmn-vad + ct-punc): ASR with timestamps
- **3D-Speaker** (CAM++): Speaker diarization
- **ffmpeg**: Audio normalization and format conversion
- **SQLite**: Primary data store
- **modelscope/huggingface_hub**: Model downloading and caching
