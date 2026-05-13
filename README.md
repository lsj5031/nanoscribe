# NanoScribe

**Transcribe voice memos with AI — privately, on your own machine.**

Drop in an audio file, record from your microphone, or send a Telegram voice message. NanoScribe transcribes it using [FunASR](https://github.com/modelscope/FunASR), shows you progress in real time, and gives you a full transcript editor with speaker labels, timestamps, and export options. Everything runs locally — your audio never leaves your computer.

<p align="center">
  <img src="screenshots/memo-editor.png" alt="NanoScribe Transcript Editor" width="720">
</p>

---

## What You Can Do

- **Transcribe audio** — Upload WAV, MP3, M4A, OGG, and more. Batch upload multiple files at once.
- **Record directly** — Use your browser microphone to capture voice memos without leaving the app.
- **Watch live progress** — See transcription happen in real time with stage-by-stage updates.
- **Edit transcripts** — Fix mistakes, rename speakers, and navigate by clicking timestamps. Your edits save automatically.
- **Identify speakers** — Automatic speaker diarization with color-coded labels for each person.
- **Search everything** — Find any memo by title or search inside transcript text.
- **Export results** — Download transcripts as TXT, JSON, or SRT files.
- **Use your GPU or the cloud** — Run models locally on your NVIDIA GPU, or connect to any OpenAI-compatible API (OpenAI, Groq, etc.).
- **Work offline** — Once models are downloaded, you don't need internet. Transcribe anywhere.
- **Install as an app** — PWA support lets you install NanoScribe as a desktop application.
- **Transcribe from Telegram** — Send voice messages to an optional Telegram bot and get transcripts back.

## Screenshots

<table>
  <tr>
    <td align="center"><b>Library</b></td>
    <td align="center"><b>Transcript Editor</b></td>
  </tr>
  <tr>
    <td><img src="screenshots/library.png" alt="Library view" width="420"></td>
    <td><img src="screenshots/memo-editor.png" alt="Transcript editor" width="420"></td>
  </tr>
  <tr>
    <td align="center"><b>Settings — Local GPU</b></td>
    <td align="center"><b>Settings — Remote API</b></td>
  </tr>
  <tr>
    <td><img src="screenshots/settings-local-gpu.png" alt="Settings with local GPU" width="420"></td>
    <td><img src="screenshots/settings.png" alt="Settings with remote API" width="420"></td>
  </tr>
</table>

---

## Getting Started

### What You Need

- **Docker** installed on your computer
- **For local GPU transcription:** An NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- **For cloud transcription:** An API key from OpenAI, Groq, or any OpenAI-compatible service (no GPU needed)

### Option 1: One Command (Recommended)

This pulls the prebuilt image and starts NanoScribe immediately:

```bash
mkdir -p data
docker run -d --name nanoscribe --gpus all \
  -p 8000:8000 -v "$(pwd)/data:/app/data" \
  --restart unless-stopped \
  ghcr.io/lsj5031/nanoscribe:latest
```

Then open **http://localhost:8000** in your browser.

> **First run:** The AI models (~2 GB) download automatically into `./data/.modelscope_cache`. This happens once.

### Option 2: Docker Compose

```bash
curl -O https://raw.githubusercontent.com/lsj5031/nanoscribe/main/compose.run.yml
docker compose -f compose.run.yml up -d
```

Then open **http://localhost:8000**.

---

## How to Use NanoScribe

### 1. Upload or Record Audio

- **Drag and drop** audio files anywhere on the page
- **Click to browse** and select files from your computer
- **Record** directly from your microphone using the record button

Supported formats: WAV, MP3, M4A, AAC, WebM, OGG, Opus. The OpenAI-compatible API endpoint additionally supports MP4, MPEG, MPGA, and FLAC.

### 2. Wait for Transcription

Once you upload a file, NanoScribe starts processing immediately:

1. **Normalizing** — Audio is converted to a consistent format
2. **Transcribing** — FunASR converts speech to text with timestamps
3. **Diarizing** — Speakers are identified and labeled (optional)
4. **Finalizing** — Results are saved and ready to edit

You'll see a progress indicator with estimated time remaining. You can navigate away and come back — processing continues in the background.

### 3. Edit Your Transcript

Click any memo to open the transcript editor:

- **Edit text** — Click any segment and type to fix transcription errors
- **Jump to audio** — Click a timestamp to seek to that moment in the recording
- **Rename speakers** — Click a speaker label to give them a real name
- **Search** — Find specific words inside the transcript
- **Playback controls** — Adjust speed, use keyboard shortcuts

All edits save automatically. You won't lose work if you refresh the page.

### 4. Export

Click the export button to download your transcript:

| Format | Best for |
|--------|----------|
| **TXT** | Plain text, notes, sharing |
| **JSON** | Programmatic use, data processing |
| **SRT** | Video subtitles, captioning |

---

## Remote API — No GPU Needed

Don't have an NVIDIA GPU? Use any OpenAI-compatible API instead:

1. Open **Settings** in NanoScribe
2. Switch the engine from "Local GPU" to "Remote API"
3. Enter your API details:

| Setting | Example |
|---------|---------|
| API URL | `https://api.openai.com/v1` |
| API Key | `sk-...` |
| Model | `whisper-1` |

NanoScribe works with any provider that supports the OpenAI `/v1/audio/transcriptions` endpoint — including **Groq**, **Together AI**, and self-hosted alternatives.

You can also set these as environment variables:

```bash
NANOSCRIBE_REMOTE_ASR_URL=https://api.openai.com/v1
NANOSCRIBE_REMOTE_ASR_API_KEY=sk-...
NANOSCRIBE_REMOTE_ASR_MODEL=whisper-1
```

---

## Telegram Bot

Get transcripts directly in Telegram. Send a voice message or audio file and receive the transcript back in seconds.

### Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and get your token
2. Copy `bot/.env.example` to `bot/.env` and fill in:
   - `TELEGRAM_TOKEN` — your bot token from BotFather
   - `ALLOWED_UIDS` — comma-separated Telegram user IDs that can use the bot
3. Start the bot alongside NanoScribe:

```bash
make dev-all
```

Or start just the bot:

```bash
make bot-up
```

### How It Works

- **Short audio (≤ 60s):** Transcribed in a single request
- **Long audio (> 60s):** Split into chunks, transcribed with progressive updates in Telegram
- All transcription happens through NanoScribe's local backend — your audio stays on your machine
- Bot transcriptions are ephemeral and don't appear in the NanoScribe library

### Supported Audio Formats

WAV, MP3, M4A, AAC, WebM, OGG, Opus, MP4, MPEG, MPGA, FLAC

### Large Files (> 20 MB)

Telegram's public API limits file downloads to 20 MB. For larger files, use a local Telegram Bot API server:

```bash
# Get API credentials from https://my.telegram.org
# Add TELEGRAM_API_ID and TELEGRAM_API_HASH to bot/.env
make bot-up-full
```

---

## Configuration

### Key Environment Variables

These are the settings most users care about. See the [full reference](#all-environment-variables) below for every available option.

| Variable | What it does | Default |
|----------|-------------|---------|
| `NANOSCRIBE_OFFLINE` | Set to `1` to prevent model downloads (use cached models) | `0` |
| `NANOSCRIBE_API_KEY` | Protect the API with a bearer token | *(none)* |
| `NANOSCRIBE_REMOTE_ASR_URL` | Remote ASR endpoint (include `/v1` prefix) | *(none)* |
| `NANOSCRIBE_REMOTE_ASR_API_KEY` | API key for the remote provider | *(none)* |
| `NANOSCRIBE_REMOTE_ASR_MODEL` | Model ID for the remote provider | `whisper-1` |

### Offline Mode

Already downloaded the models and want to run without internet?

```yaml
environment:
  - HF_HUB_OFFLINE=1
  - NANOSCRIBE_OFFLINE=1
```

This prevents any network requests for model updates.

---

## API Access

NanoScribe exposes an OpenAI-compatible endpoint at `/v1/audio/transcriptions`. You can use it with any tool or library that works with the OpenAI transcription API:

```bash
curl http://localhost:8000/v1/audio/transcriptions \
  -F "file=@recording.mp3" \
  -F "model=whisper-1" \
  -F "response_format=verbose_json"
```

If you set `NANOSCRIBE_API_KEY`, include it as a Bearer token:

```bash
curl http://localhost:8000/v1/audio/transcriptions \
  -H "Authorization: Bearer your-api-key" \
  -F "file=@recording.mp3" \
  -F "model=whisper-1"
```

---

## For Developers

### Building from Source

```bash
git clone https://github.com/lsj5031/nanoscribe.git
cd nanoscribe

# Build the dev image
make build

# Start the dev server with hot reload
make dev

# On first run, the frontend SPA is built automatically.
# Open http://localhost:8000 once the build completes.
```

### Make Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start dev environment with hot reload |
| `make dev-all` | Start NanoScribe + Telegram bot |
| `make shell` | Open a shell inside the container |
| `make check` | Run all quality checks (lint, format, typecheck, tests) |
| `make backend-check` | Backend checks (ruff, ty) |
| `make frontend-check` | Frontend checks (svelte-check, prettier) |
| `make backend-test` | Run the pytest suite |
| `make build` | Build the dev Docker image |
| `make build-prod` | Build the production image |
| `make clean` | Remove built images and stop containers |
| `make hooks-install` | Install pre-commit hooks |

### Project Structure

```
bot/                    # Telegram bot (aiogram)
frontend/               # SvelteKit SPA
  src/
    lib/components/     # UI components
    lib/stores/         # Reactive state stores
    routes/             # Page routes
backend/                # FastAPI backend
  app/
    api/                # REST endpoints
    core/               # Config and dependencies
    db/                 # SQLite and migrations
    schemas/            # Pydantic models
    services/           # Business logic
  tests/                # pytest suite
data/                   # Persistent storage (bind-mounted)
```

### Storage Layout

```
/app/data/
  nanoscribe.db              # SQLite database
  .modelscope_cache/         # Downloaded AI models
  memos/
    <memo_id>/
      source.original        # Original uploaded audio
      normalized.wav         # Normalized 16kHz mono WAV
      waveform.json          # Waveform peaks for visualization
      transcript.raw.json    # Raw FunASR output
      transcript.final.json  # Editor-ready segments
      exports/               # Generated exports (txt, json, srt)
```

### AI Models

NanoScribe uses these FunASR models, downloaded automatically to `data/.modelscope_cache/`:

| Model | Purpose |
|-------|---------|
| Fun-ASR-Nano-2512 | Speech recognition with timestamps |
| fsmn-vad | Voice activity detection |
| ct-punc | Punctuation restoration |
| CAM++ | Speaker diarization |

Models load onto the GPU during inference and unload afterward to conserve VRAM.

### Full API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system/health` | GET | Component health status |
| `/api/system/capabilities` | GET | Runtime capability manifest |
| `/api/system/readiness` | GET | Per-model readiness status |
| `/api/system/status` | GET | System status and storage info |
| `/api/system/settings/engine` | GET | Current engine configuration |
| `/api/system/settings/engine` | PUT | Update engine configuration |
| `/api/memos` | GET / POST | List or upload memos |
| `/api/memos/{id}` | GET / DELETE | Get or delete a memo |
| `/api/memos/{id}/audio` | GET | Stream audio file |
| `/api/memos/{id}/waveform` | GET | Waveform peak data |
| `/api/memos/{id}/segments` | GET / PATCH | Get or edit transcript segments |
| `/api/memos/{id}/speakers` | GET / PATCH | Get or rename speakers |
| `/api/memos/{id}/reprocess` | POST | Re-run transcription |
| `/api/memos/{id}/regenerate-diarization` | POST | Re-run diarization only |
| `/api/memos/{id}/retry` | POST | Retry last failed job |
| `/api/memos/{id}/jobs` | GET | List jobs for a memo |
| `/api/memos/{id}/export` | GET | Export (txt, json, srt) |
| `/api/jobs/{id}` | GET | Job status |
| `/api/jobs/{id}/events` | GET | SSE event stream |
| `/api/jobs/{id}/cancel` | POST | Cancel a running job |
| `/api/search` | GET | Search memos and transcripts |
| `/v1/audio/transcriptions` | POST | OpenAI-compatible transcription |
| `/v1/models` | GET | OpenAI-compatible model list |

### All Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NANOSCRIBE_DATA_DIR` | `/app/data` | Root directory for all persistent data |
| `NANOSCRIBE_STATIC_DIR` | `/app/static` | Path to built frontend SPA |
| `NANOSCRIBE_OFFLINE` | `0` | Set to `1` to skip remote model checks/downloads |
| `NANOSCRIBE_API_KEY` | *(empty)* | Bearer token for the OpenAI-compatible endpoint |
| `NANOSCRIBE_REMOTE_ASR_URL` | *(empty)* | Remote ASR endpoint URL (include `/v1` prefix) |
| `NANOSCRIBE_REMOTE_ASR_API_KEY` | *(empty)* | API key for the remote ASR provider |
| `NANOSCRIBE_REMOTE_ASR_MODEL` | `whisper-1` | Model ID for the remote ASR provider |
| `NANOSCRIBE_REMOTE_ASR_TIMEOUT` | `900` | Remote ASR request timeout in seconds |
| `NANOSCRIBE_KEEP_MODELS_WARM` | *(empty)* | Keep models on GPU: `1`=always, `0`=never, empty=auto |
| `NANOSCRIBE_VAD_MAX_CHUNK_MS` | `0` | Max VAD chunk size in ms (`0` = auto-detect from VRAM) |
| `NANOSCRIBE_VAD_MERGE_GAP_MS` | `800` | Gap (ms) between VAD segments to merge |
| `NANOSCRIBE_VAD_CHUNK_BUFFER_MS` | `200` | Buffer (ms) added to each VAD chunk boundary |
| `NANOSCRIBE_VAD_MIN_CHUNK_MS` | `400` | Minimum VAD chunk duration in ms |
| `HF_HUB_OFFLINE` | `0` | Set to `1` to prevent HuggingFace downloads |
| `MODELSCOPE_CACHE` | `/app/data/.modelscope_cache` | ModelScope model cache directory |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | CUDA memory allocator config |

### Development Workflow

All development happens inside Docker — you don't need Python, Node.js, or pnpm installed on your host.

**Backend:**

```bash
make shell   # enter the container
cd /app/backend
ruff format .          # Auto-format
ruff check .           # Lint
ty check .             # Type check
python -m pytest       # Run tests
```

**Frontend:**

```bash
make shell   # enter the container
cd /app/frontend
pnpm dev               # Dev server with HMR
pnpm check             # Svelte type checking
pnpm format:check      # Prettier format check
pnpm build             # Production build
```

**CI note:** The CI workflow skips GPU-dependent tests (`test_transcription.py`, `test_diarization.py`) since GitHub runners lack NVIDIA GPUs. These tests can only run locally with `make backend-test`.

To reproduce the exact CI path for frontend checks:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm svelte-kit sync
pnpm check
pnpm format:check
```

---

## Links

- **GitHub** — [github.com/lsj5031/nanoscribe](https://github.com/lsj5031/nanoscribe)
- **FunASR** — [github.com/modelscope/FunASR](https://github.com/modelscope/FunASR) (upstream ASR engine)
- **ModelScope** — [modelscope.cn](https://www.modelscope.cn) (model hub)

Built with ❤️ by [@lsj5031](https://github.com/lsj5031). Contributions welcome — open an issue or PR on GitHub.


