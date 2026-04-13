---
name: backend-worker
description: Implements backend features — FastAPI endpoints, services, database, FunASR integration
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Backend features: API endpoints, services, database schema/migrations, FunASR integration, 3D-Speaker integration, job processing, export generation.

## Required Skills

None. All work is done with file editing tools and shell commands inside Docker.

## Work Procedure

1. **Read context:** Read `mission.md`, this AGENTS.md, and `.factory/library/architecture.md` for full context. Read the feature description carefully.

2. **Write tests first (TDD):**
   - Create test file(s) under `backend/tests/` for the feature
   - Write failing tests that define expected behavior
   - Tests must exercise the API contract, service behavior, or data model
   - Run tests to confirm they fail: `docker compose exec funasr bash -c "cd /app/backend && python -m pytest tests/ -x --tb=short"`

3. **Implement to make tests pass:**
   - Create/edit source files under `backend/app/`
   - Follow existing patterns: services in `app/services/`, API routes in `app/api/`, schemas in `app/schemas/`, DB in `app/db/`
   - Keep services small and direct (SPEC §25)
   - Use plain sqlite3 with WAL mode for database access

4. **Run quality checks:**
   - `docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check . && ty check ."`
   - Fix any issues found

5. **Run full test suite:**
   - `docker compose exec funasr bash -c "cd /app/backend && python -m pytest tests/ -x --tb=short"`
   - All tests must pass

6. **Manual verification:**
   - Start the app if needed: `docker compose exec funasr bash -c "cd /app/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"`
   - Test the endpoint with curl
   - Verify the response matches expected behavior

7. **Commit and hand off.**

## Example Handoff

```json
{
  "salientSummary": "Implemented POST /api/memos multipart upload endpoint. Creates memo and job rows, stores original file, returns 201. Added 6 test cases covering single upload, batch upload, empty upload, unsupported format, and corrupt file.",
  "whatWasImplemented": "POST /api/memos endpoint with multipart upload, MemoService.create_from_upload(), JobService.create_transcription_job(), migration 001 creating memos and jobs tables, and 6 pytest test cases.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "docker compose exec funasr bash -c 'cd /app/backend && python -m pytest tests/test_upload.py -x'", "exitCode": 0, "observation": "6 tests passed" },
      { "command": "docker compose exec funasr bash -c 'cd /app/backend && ruff check .'", "exitCode": 0, "observation": "No issues found" },
      { "command": "curl -X POST http://localhost:8000/api/memos -F 'files[]=@test.wav'", "exitCode": 0, "observation": "201 Created with memo and job objects" }
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      { "file": "backend/tests/test_upload.py", "cases": [
        { "name": "test_single_upload_creates_memo_and_job", "verifies": "POST /api/memos creates one memo and one job" },
        { "name": "test_batch_upload_creates_multiple_memos", "verifies": "Multiple files create independent memos and jobs" },
        { "name": "test_empty_upload_returns_422", "verifies": "No files returns validation error" },
        { "name": "test_unsupported_format_returns_422", "verifies": "Non-audio format rejected with clear error" },
        { "name": "test_default_title_from_filename", "verifies": "Title defaults to filename without extension" },
        { "name": "test_optional_params_stored", "verifies": "title, language, hotwords params stored on memo" }
      ]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature depends on a frontend component that doesn't exist yet
- Feature requires changes to the Dockerfile or docker-compose.yml
- Requirements are ambiguous or contradictory with existing implementation
- Existing bugs block progress that can't be fixed within the feature scope
