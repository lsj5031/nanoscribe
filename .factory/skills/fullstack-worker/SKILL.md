---
name: fullstack-worker
description: Implements features spanning backend and frontend — end-to-end features requiring coordinated changes
---

# Fullstack Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features that require coordinated changes across both backend and frontend: API endpoint + UI component, data model + state management, service + component integration.

## Required Skills

None. All work is done with file editing tools, shell commands, and browser verification.

## Work Procedure

1. **Read context:** Read `mission.md`, this AGENTS.md, and `.factory/library/architecture.md` for full context. Read the feature description carefully. Understand both the backend and frontend requirements.

2. **Write backend tests first (TDD):**
   - Create test file(s) under `backend/tests/` for the backend portion
   - Write failing tests for API contracts and service behavior
   - Run tests to confirm they fail

3. **Implement backend:**
   - Create/edit source files under `backend/app/`
   - Follow existing patterns
   - Run backend tests: `docker compose exec funasr bash -c "cd /app/backend && python -m pytest tests/ -x --tb=short"`

4. **Implement frontend:**
   - Create/edit files under `frontend/src/`
   - Use Svelte 5 runes, Tailwind CSS v4
   - Ensure API integration works with the backend changes

5. **Run all quality checks:**
   - Backend: `docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check . && ty check ."`
   - Frontend: `docker compose exec funasr bash -c "cd /app/frontend && pnpm check && pnpm format:check"`

6. **Run full test suite:**
   - `docker compose exec funasr bash -c "cd /app/backend && python -m pytest tests/ -x --tb=short"`

7. **Manual end-to-end verification:**
   - Start the full application
   - Use `agent-browser` skill to test the complete user flow
   - Verify backend API responses and frontend rendering
   - Test error states and edge cases

8. **Commit and hand off.**

## Example Handoff

```json
{
  "salientSummary": "Implemented transcript editor with two-pane layout, wavesurfer.js waveform, segment editing with autosave, and optimistic concurrency (409 on stale revision). Full-stack feature: PATCH/GET segments API + editor UI component.",
  "whatWasImplemented": "Backend: PATCH /api/memos/{id}/segments endpoint with base_revision conflict detection, GET /api/memos/{id}/segments with ordered segments and revision. Frontend: editor page at /memos/[memoId] with resizable panes, wavesurfer.js integration, inline segment editing, autosave on debounce, click-to-seek, keyboard shortcuts (Space, arrows, Up/Down, Enter, Escape).",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "docker compose exec funasr bash -c 'cd /app/backend && python -m pytest tests/test_segments.py -x'", "exitCode": 0, "observation": "8 tests passed including conflict detection" },
      { "command": "docker compose exec funasr bash -c 'cd /app/backend && ruff check . && ty check .'", "exitCode": 0, "observation": "No issues" },
      { "command": "docker compose exec funasr bash -c 'cd /app/frontend && pnpm check'", "exitCode": 0, "observation": "No type errors" }
    ],
    "interactiveChecks": [
      { "action": "Open editor for completed memo", "observed": "Two-pane layout renders, waveform loads, segments display in right pane" },
      { "action": "Click play button", "observed": "Audio plays, playhead moves across waveform, current segment highlights" },
      { "action": "Click timestamp on segment", "observed": "Audio seeks to segment start, segment highlights" },
      { "action": "Edit segment text, wait for autosave", "observed": "PATCH request sent after debounce, revision increments, toast confirms save" },
      { "action": "Press Space", "observed": "Audio toggles play/pause" },
      { "action": "Submit stale revision", "observed": "409 returned, UI shows conflict with latest state" }
    ]
  },
  "tests": {
    "added": [
      { "file": "backend/tests/test_segments.py", "cases": [
        { "name": "test_get_segments_ordered", "verifies": "Segments returned in ordinal order with revision" },
        { "name": "test_patch_segments_increments_revision", "verifies": "Successful edit increments revision" },
        { "name": "test_patch_segments_conflict_returns_409", "verifies": "Stale revision returns 409 with latest state" },
        { "name": "test_patch_segments_validation", "verifies": "Missing fields return 422" }
      ]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature requires changes to the Dockerfile or docker-compose.yml
- Backend or frontend dependency needs to be added that affects other features
- Requirements are ambiguous about the interaction between backend and frontend
- The feature scope is too large for a single session
