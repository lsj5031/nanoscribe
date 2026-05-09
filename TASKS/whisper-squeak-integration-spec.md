# WhisperSqueak Integration Spec

> Integration of the [WhisperSqueak](https://github.com/lsj5031/WhisperSqueak) Telegram bot
> into NanoScribe, using NanoScribe's FunASR transcription pipeline as the backend.

## 1. Summary

Add a Telegram bot (`bot/`) as a separate Docker Compose service that receives voice
messages and audio files via Telegram, transcribes them using NanoScribe's local
FunASR pipeline (via HTTP), and returns the transcript inline as a Telegram message.

The bot runs in its own container, on the same Docker network as NanoScribe. No
authentication is required between containers (trusted internal network).

## 2. Integration Architecture

```
┌────────────────────────────────────────────────────┐
│                    Docker Host                      │
│                                                    │
│  ┌──────────────┐    HTTP (no auth)    ┌─────────┐ │
│  │  bot/        │ ──────────────────>  │ Nano-   │ │
│  │  aiogram     │   /v1/audio/        │ Scribe  │ │
│  │  (Telegram)  │   transcriptions    │ FastAPI │ │
│  │              │ <────────────────── │ :8000   │ │
│  │  pydub/ffmpeg│   JSON transcript   │         │ │
│  └──────────────┘                     │ FunASR  │ │
│        │                              │ GPU     │ │
│        │ Telegram API                 └─────────┘ │
│  ┌─────┴────────┐                                 │
│  │ telegram-api │  (optional, >20MB)              │
│  │ local server │                                 │
│  └──────────────┘                                 │
└────────────────────────────────────────────────────┘
```

### 2.1 Service Communication

- Bot → NanoScribe: HTTP on internal Docker network at `http://funasr:8000`
  (the service name from `docker-compose.yml`)
- No auth required between containers (Q8: C)
- NanoScribe's optional `NANOSCRIBE_API_KEY` is NOT set/used for bot traffic

### 2.2 Container Topology

- **`funasr`** — existing NanoScribe FastAPI + FunASR (unchanged)
- **`bot`** — new container: Python 3.13-alpine + aiogram + ffmpeg + pydub
- **`telegram-api`** — optional local Telegram Bot API server (large file support)
- All on the default Compose network (or shared bridge network)

## 3. Repository Structure

```
bot/                          # NEW: Telegram bot code
  bot.py                      # Main bot logic (aiogram)
  sse_parser.py               # SSE stream parser (if needed)
  requirements.txt            # Python dependencies
  Dockerfile                  # Bot container build
  .env.example                # Environment template (bot-specific)

docker-compose.yml            # MODIFIED: add bot + telegram-api services
.env.example                  # NEW/updated: top-level env template
```

The bot lives at `bot/` (Q15: B), separate from the `backend/` tree.

## 4. Bot Features

### 4.1 Core — Keep from Original WhisperSqueak

| Feature | Notes |
|---------|-------|
| Voice message transcription | Receive Telegram voice notes → transcribe → reply |
| Audio file transcription | MP3, WAV, OGG, M4A, FLAC, etc. |
| User whitelist (`ALLOWED_UIDS`) | Comma-separated Telegram user IDs; unknown users rejected |
| Long audio handling | Split into chunks, progressive result updates |
| `/start` command | Welcome message, brief usage info |
| `/help` command | Usage instructions and supported formats |
| Language auto-detect | Rely on NanoScribe's auto-detection (no user-level lang prefs) |

### 4.2 Removed from Original WhisperSqueak

| Feature | Reason |
|---------|--------|
| `/model` command | NanoScribe uses a fixed FunASR preset — no model switching |
| `/language` command | Q11: B — auto-detect only, no per-user language persistence |
| Per-user settings JSON | No persistent user preferences needed |
| External Faster Whisper Server | Replaced by NanoScribe's FunASR pipeline |
| `WHISPER_URL` / `WHISPER_API_KEY` env vars | Replaced by `NANOSCRIBE_URL` |

### 4.3 Transcription Flow

```
User sends voice/audio → Bot receives message
  ├─ Check ALLOWED_UIDS whitelist
  ├─ Download audio file from Telegram
  ├─ Determine duration (pydub)
  │
  ├─ Short audio (≤ 60s):
  │   └─ POST to http://funasr:8000/v1/audio/transcriptions
  │      (multipart/form-data, response_format=verbose_json)
  │   └─ Parse response → format as Telegram message → reply
  │
  └─ Long audio (> 60s):
      └─ Split into ~60s chunks with 2s overlap (ffmpeg/pydub)
      └─ POST each chunk sequentially
      └─ Edit the Telegram message progressively as chunks complete
      └─ Final: full transcript with timestamps
```

### 4.4 Long Audio Chunking Details

Reproduce the original WhisperSqueak chunking logic:
- Split audio into chunks of approximately 60 seconds
- 2-second overlap between consecutive chunks to avoid cutting words
- Each chunk sent as a separate HTTP request to NanoScribe
- Results concatenated with deduplication of overlap text
- Progressive editing of the sent Telegram message as each chunk completes

## 5. NanoScribe Backend Changes

### 5.1 Existing Endpoint Used

The bot primarily calls NanoScribe's existing **OpenAI-compatible endpoint**:

```
POST /v1/audio/transcriptions
```

This endpoint is already production-ready:
- Accepts multipart/form-data with audio file
- Runs the full FunASR pipeline (VAD → ASR → Punc)
- Returns `verbose_json` with segments, timestamps, text
- Synchronous (blocks until complete) — acceptable since the bot chunks long audio
- No auth when `NANOSCRIBE_API_KEY` is unset

### 5.2 New Endpoint (Phase 2 / Optional Enhancement)

A new SSE-based streaming transcription endpoint for the bot:

```
POST /api/bot/transcribe
```

**Purpose:** Accept an audio file and return transcription results progressively
via SSE, so the bot can relay real-time chunk-level progress to the Telegram user
without the bot doing its own chunking.

**Request:**
- `POST /api/bot/transcribe`
- `multipart/form-data`: `file` (audio), optional `hotwords`, optional `language`

**SSE Event Stream Response:**
```
event: progress
data: {"stage": "transcribing", "chunks_done": 1, "total_chunks": 5}

event: partial
data: {"text": "Hello world...", "segments": [...]}

event: completed
data: {"text": "Full transcript...", "segments": [...], "duration_ms": 42000}

event: failed
data: {"error_code": "ASR_FAILED", "error_message": "..."}
```

**Implementation notes:**
- Modeled after the existing job SSE system in `backend/app/services/sse.py`
- Reuses `TranscriptionModels.transcribe()` with the existing `chunk_callback`
- Stateless — no job/memo rows created (like the OpenAI-compat endpoint)
- Runs on the same worker lock (serialised GPU access)
- No auth required (trusted internal network)

**This is a Phase 2 enhancement.** The initial integration works with the bot
doing its own chunking + calling the existing `/v1/audio/transcriptions` per chunk.

## 6. Bot Implementation Details

### 6.1 Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Framework | aiogram 3.13.1 | Same as original WhisperSqueak (Q9: A) |
| HTTP client | httpx | Async, already a NanoScribe dep |
| Audio processing | pydub + ffmpeg | Same as original; ffmpeg already in image |
| Python version | 3.13-alpine | Same as original WhisperSqueak Dockerfile |
| Env loading | python-dotenv | Same as original |
| Package manager | uv (pip) | Same as original; fast, modern |

### 6.2 Dependencies (`bot/requirements.txt`)

```
aiogram==3.13.1
httpx>=0.27.0
pydub==0.25.1
audioop-lts
python-dotenv==1.0.1
```

Removed from original: `aiohttp` (not needed — httpx is sufficient).

### 6.3 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_TOKEN` | Yes | — | Bot token from @BotFather |
| `ALLOWED_UIDS` | Yes | — | Comma-separated Telegram user IDs |
| `NANOSCRIBE_URL` | No | `http://funasr:8000` | NanoScribe backend URL |
| `TELEGRAM_API_ID` | No | — | For local API server (>20MB files) |
| `TELEGRAM_API_HASH` | No | — | For local API server |
| `TELEGRAM_API_URL` | No | `http://telegram-api:8081` | Local API server URL |

### 6.4 Bot Commands

```
/start  — Welcome message: "Hi! I transcribe voice messages and audio files
           using FunASR. Send me a voice note or audio file to get started."
/help   — Usage: "Supported formats: MP3, WAV, OGG, M4A, FLAC, WebM, Opus.
           Send any voice message or audio file. Long audio is processed in
           chunks with progressive results."
```

### 6.5 Whitelist Enforcement

- Read `ALLOWED_UIDS` from env, split by comma, parse as integers
- On every message: check `message.from_user.id` against whitelist
- If not whitelisted: silently ignore or reply with a polite "Access denied" message
- Apply to both private chats and group chats (if added to groups)

### 6.6 Supported Audio Formats

All formats supported by NanoScribe's normalization pipeline:
`wav`, `mp3`, `m4a`, `aac`, `webm`, `ogg`, `opus`, `mp4`, `mpeg`, `mpga`, `flac`

## 7. Docker Configuration

### 7.1 Bot Dockerfile (`bot/Dockerfile`)

```dockerfile
# Builder stage
FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --compile-bytecode --no-cache -r requirements.txt

# Runtime stage
FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache ffmpeg
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY bot.py sse_parser.py ./
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://localhost:8080/health || exit 1
CMD ["python", "bot.py"]
```

### 7.2 Docker Compose Changes

Add to the existing `docker-compose.yml`:

```yaml
  # ── Telegram Bot ─────────────────────────────────────────────────
  bot:
    build:
      context: ./bot
    container_name: nanoscribe-bot
    restart: unless-stopped
    env_file:
      - ./bot/.env
    volumes:
      - ./bot/bot.py:/app/bot.py:ro
      - ./bot/sse_parser.py:/app/sse_parser.py:ro
    tmpfs:
      - /tmp:size=2G
    depends_on:
      - funasr
    networks:
      - default

  # ── Telegram Local API Server (optional, for files >20MB) ───────
  telegram-api:
    image: aiogram/telegram-bot-api:latest
    container_name: telegram-api
    restart: unless-stopped
    profiles:
      - telegram-api      # Only started when explicitly requested
    environment:
      - TELEGRAM_API_ID=${TELEGRAM_API_ID:-}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH:-}
      - TELEGRAM_LOCAL=true
    volumes:
      - telegram-api-data:/var/lib/telegram-bot-api
    healthcheck:
      test: ["CMD-SHELL", "wget -qS -O /dev/null http://127.0.0.1:8081 2>&1 | grep -q 'HTTP/'"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - default

volumes:
  telegram-api-data:
```

Key decisions:
- `telegram-api` uses a Compose profile so it's opt-in (`docker compose --profile telegram-api up`)
- Both services join the default Compose network so they can reach `funasr:8000`
- Bot uses `tmpfs` for `/tmp` (2GB) for temporary audio chunk files
- Bot env file at `bot/.env` (separate from NanoScribe's env vars)

### 7.3 Production Compose (`compose.run.yml`)

Same additions as above, but `funasr` service references the GHCR image as it
already does. The bot and telegram-api services are identical between dev and prod.

## 8. NanoScribe Backend Changes Summary

| Change | File | Purpose |
|--------|------|---------|
| New endpoint (Phase 2) | `backend/app/api/bot.py` | SSE streaming transcription for bot |
| Register router (Phase 2) | `backend/app/main.py` | Include bot router |
| New service (Phase 2) | `backend/app/services/bot_transcribe.py` | Stateless streaming transcription logic |
| No auth for bot endpoint | `backend/app/api/bot.py` | Skip API key check on internal endpoints |

### 8.1 Phase 1 (Initial) — No Backend Changes

The initial integration requires **zero changes to NanoScribe's backend**.
The bot uses the existing `/v1/audio/transcriptions` endpoint, which already:
- Accepts multipart audio uploads
- Returns `verbose_json` with segments and timestamps
- Works without auth when `NANOSCRIBE_API_KEY` is unset (the default)

### 8.2 Phase 2 (Enhancement) — Streaming Endpoint

Add a bot-dedicated endpoint that provides SSE-based progressive transcription
so the bot doesn't need to do its own chunking.

## 9. Environment Configuration

### 9.1 New Top-Level `.env.example`

```bash
# === Telegram Bot ===
# Bot token from @BotFather (required for bot service)
TELEGRAM_TOKEN=

# Comma-separated Telegram user IDs allowed to use the bot (required)
ALLOWED_UIDS=

# Optional: Telegram API credentials for local API server (>20MB files)
# Get from https://my.telegram.org
# TELEGRAM_API_ID=
# TELEGRAM_API_HASH=

# === NanoScribe (existing) ===
# These are documented in README.md — kept here for reference
# HOST_PORT=8000
# BASE_IMAGE=nvidia/cuda:12.4.1-runtime-ubuntu22.04
```

### 9.2 Bot `.env` Template (`bot/.env.example`)

```bash
# Telegram Bot Token (required)
TELEGRAM_TOKEN=

# Allowed Telegram User IDs (required, comma-separated)
ALLOWED_UIDS=

# NanoScribe backend URL (optional, default: http://funasr:8000)
NANOSCRIBE_URL=http://funasr:8000

# Optional: Telegram Local API Server (for files >20MB)
# TELEGRAM_API_ID=
# TELEGRAM_API_HASH=
# TELEGRAM_API_URL=http://telegram-api:8081
```

## 10. Makefile Additions

```makefile
# ── Bot ────────────────────────────────────────────────────────────

bot-build:
	docker compose build bot

bot-up:
	docker compose up -d bot

bot-logs:
	docker compose logs -f bot

bot-shell:
	docker compose exec bot /bin/sh

# Start with local API server for large files
bot-up-full:
	docker compose --profile telegram-api up -d bot telegram-api

# Start everything (NanoScribe + bot)
dev-all:
	docker compose up -d
```

## 11. Testing Plan

### 11.1 Manual Testing

1. Set up `.env` with `TELEGRAM_TOKEN` and `ALLOWED_UIDS`
2. `make dev-all` — start NanoScribe + bot
3. Wait for FunASR models to download/cache (check `http://localhost:8000/api/system/capabilities`)
4. Send a short voice message to the bot → expect transcript reply
5. Send a long audio file (> 60s) → expect progressive chunk updates
6. Send from a non-whitelisted user → expect rejection
7. Send `/start` and `/help` → expect command responses
8. Send an unsupported format (e.g., PDF) → expect error message
9. Send while NanoScribe is offline → expect graceful error

### 11.2 Automated Testing (Phase 2+)

- Bot logic unit tests (message handler, chunking, whitelist check)
- Integration test: mock NanoScribe endpoint, verify bot sends correct requests

## 12. Files Changed / Created

### New Files
| File | Purpose |
|------|---------|
| `bot/bot.py` | Main Telegram bot |
| `bot/sse_parser.py` | SSE stream parser (from original, if needed) |
| `bot/requirements.txt` | Python dependencies |
| `bot/Dockerfile` | Bot container build |
| `bot/.env.example` | Bot env template |
| `.env.example` | Top-level env template (updated) |
| `TASKS/whisper-squeak-integration-spec.md` | This spec |

### Modified Files
| File | Change |
|------|--------|
| `docker-compose.yml` | Add `bot` and `telegram-api` services |
| `compose.run.yml` | Add `bot` and `telegram-api` services |
| `Makefile` | Add bot-related targets |
| `README.md` | Document bot setup and usage |

### Phase 2 Backend Changes (New Files)
| File | Purpose |
|------|---------|
| `backend/app/api/bot.py` | SSE streaming endpoint for bot |
| `backend/app/services/bot_transcribe.py` | Stateless transcription with SSE |

### Phase 2 Backend Changes (Modified Files)
| File | Change |
|------|--------|
| `backend/app/main.py` | Register bot API router |

## 13. Out of Scope

- Cross-memo speaker memory or any library integration
- Bot transcriptions appearing in NanoScribe's web UI memo library
- Per-user language preferences or settings persistence
- Multi-user accounts or authentication beyond whitelist
- Bot commands beyond `/start` and `/help`
- Model selection via bot
- Any frontend changes

## 14. Implementation Order

### Phase 1 — Working Bot (Minimal Changes)

1. Create `bot/` directory with `bot.py`, `requirements.txt`, `Dockerfile`, `.env.example`
2. Implement bot: aiogram setup, whitelist, `/start`, `/help`
3. Implement transcription: download audio → POST to `/v1/audio/transcriptions` → reply
4. Implement long audio chunking: split → POST each chunk → progressive message updates
5. Add bot and telegram-api services to `docker-compose.yml` and `compose.run.yml`
6. Add Makefile targets
7. Update README

### Phase 2 — Streaming Endpoint (Enhancement)

1. Create `backend/app/services/bot_transcribe.py` — stateless SSE transcription
2. Create `backend/app/api/bot.py` — new `/api/bot/transcribe` endpoint
3. Register in `main.py`
4. Update bot to use streaming endpoint for long audio (simplifies bot code)

## 15. Open Questions / Decisions

| # | Question | Resolution |
|---|----------|------------|
| Q1 | Integration depth | Deep: bot uses NanoScribe backend |
| Q2 | Which ASR pipeline | NanoScribe's FunASR |
| Q3 | Shared memo library | No — bot transcriptions are ephemeral |
| Q4 | Has Telegram token | Yes |
| Q5 | Transcript storage | Return inline as Telegram message (ephemeral) |
| Q6 | Features to keep | Whitelist + long audio handling |
| Q7 | Container topology | Separate container, same Docker network |
| Q8 | Bot-NanoScribe auth | No auth (trusted internal network) |
| Q9 | Telegram framework | aiogram 3.x (same as original) |
| Q10 | Local API server | Yes, as opt-in Compose profile |
| Q11 | Language preferences | Auto-detect only, no per-user settings |
| Q12 | Communication method | HTTP to `http://funasr:8000` |
| Q13 | Long audio approach | Phase 1: bot chunks + existing endpoint; Phase 2: new SSE endpoint |
| Q14 | Bot commands | `/start` and `/help` only |
| Q15 | Code location | `bot/` at repo root |
