# FunASR-Plus: Enhanced Transcription & Workflow Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge the gap between FunASR (high-performance engine) and auto-subs (workflow integration) by adding advanced export formats, smart segmentation, and LLM-based translation to the `~/code/funasr` project.

**Architecture:** 
- Enhance `app.services.export` with new formatters (VTT, EDL, XML).
- Create `app.services.refine` for smart segmentation logic (punctuation, CPS limits).
- Create `app.services.translate` for LLM-based translation using OpenAI-compatible APIs.
- Add new endpoints to `app.api.export` and a new `app.api.refine` router.

**Tech Stack:** Python (FastAPI), SQLite, OpenAI-compatible APIs (for translation), jinja2 (for XML/EDL templates).

---

### Task 1: Foundation & VTT Support

**Files:**
- Modify: `/home/leo/code/funasr/backend/app/services/export.py`
- Modify: `/home/leo/code/funasr/backend/app/api/export.py`

- [ ] **Step 1: Add VTT timestamp formatter and export function in services**
```python
def _ms_to_vtt_timestamp(ms: int) -> str:
    """Convert milliseconds to VTT timestamp format HH:MM:SS.mmm."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

def export_vtt(db_path: str | Path, memo_id: str) -> tuple[str, str] | None:
    # Logic similar to export_srt but with WEBVTT header and . separator
    ...
```

- [ ] **Step 2: Update API router to support 'vtt' format**
```python
SUPPORTED_FORMATS = {"txt", "json", "srt", "vtt"}
```

- [ ] **Step 3: Test VTT export via curl**
Run: `curl http://localhost:8000/api/memos/{id}/export?format=vtt`
Expected: 200 OK with WEBVTT header.

---

### Task 2: Smart Segmentation Service

**Files:**
- Create: `/home/leo/code/funasr/backend/app/services/refine.py`
- Create: `/home/leo/code/funasr/backend/app/api/refine.py`
- Modify: `/home/leo/code/funasr/backend/app/main.py`

- [ ] **Step 1: Implement smart splitting logic**
Focus on:
- Splitting at punctuation (., ?, !).
- Enforcing Max CPS (Characters Per Second).
- Enforcing Max line length.

- [ ] **Step 2: Create API endpoint for "Re-segmentation"**
`POST /api/memos/{id}/resegment` - Takes parameters like `max_cps`, `max_length`.

- [ ] **Step 3: Register router in main.py**

---

### Task 3: DaVinci Resolve Integration (EDL/XML)

**Files:**
- Create: `/home/leo/code/funasr/backend/app/services/templates/davinci_fcpxml.xml`
- Modify: `/home/leo/code/funasr/backend/app/services/export.py`

- [ ] **Step 1: Create FCPXML template for subtitles**
Use jinja2 to inject segments into an FCPXML structure that DaVinci Resolve can import as a subtitle track.

- [ ] **Step 2: Implement `export_fcpxml` in export service**

- [ ] **Step 3: Add 'fcpxml' to supported formats in API**

---

### Task 4: LLM Translation Pipeline

**Files:**
- Create: `/home/leo/code/funasr/backend/app/services/translate.py`
- Create: `/home/leo/code/funasr/backend/app/api/translate.py`

- [ ] **Step 1: Implement LLM translation client**
Use `openai` python package to call any compatible API (Google AI Studio, local llama-cpp, etc.).

- [ ] **Step 2: Batch processing of segments**
Group segments into chunks of ~500-1000 tokens to preserve context during translation.

- [ ] **Step 3: Bilingual export support**
Modify export functions to optionally include `translated_text` if available.

---

### Task 5: Rich Subtitles (SenseVoice Events)

**Files:**
- Modify: `/home/leo/code/funasr/backend/app/services/export.py`

- [ ] **Step 1: Parse SenseVoice tags in segments**
Look for `[Laughter]`, `[Music]`, etc.

- [ ] **Step 2: Apply styling in SRT/VTT/XML**
Example: `<font color="#FFD700">[Laughter]</font>` for SRT/VTT (basic HTML support).

---

## Execution Handoff

Plan complete and saved to `TASKS/funasr-plus-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
