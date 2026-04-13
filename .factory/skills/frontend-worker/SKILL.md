---
name: frontend-worker
description: Implements frontend features — SvelteKit components, pages, state management, UI/UX
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Frontend features: SvelteKit pages, components, state management (Svelte 5 runes), Tailwind styling, wavesurfer.js integration, MediaRecorder recording, PWA setup, keyboard shortcuts, SSE consumption.

## Required Skills

None. All work is done with file editing tools and browser/shell commands.

## Work Procedure

1. **Read context:** Read `mission.md`, this AGENTS.md, and `.factory/library/architecture.md` for full context. Read the feature description carefully.

2. **Implement the feature:**
   - Create/edit files under `frontend/src/`
   - Use Svelte 5 runes ($state, $derived, $effect, $props)
   - Follow existing component patterns in the project
   - Use Tailwind CSS v4 utility classes for styling
   - Dark mode default with teal accent `#00d4ff`
   - Ensure ARIA labels and keyboard accessibility from the start

3. **Run quality checks:**
   - `docker compose exec funasr bash -c "cd /app/frontend && pnpm check"` (svelte-check)
   - `docker compose exec funasr bash -c "cd /app/frontend && pnpm format:check"` (Prettier)
   - Fix any type errors or formatting issues

4. **Manual verification with browser:**
   - Ensure app is running (frontend dev server on port 5173 or production build)
   - Use `agent-browser` skill to verify UI renders correctly
   - Test interactive elements (click, type, keyboard shortcuts)
   - Verify dark mode rendering
   - Check for console errors
   - Each tested flow = one `interactiveChecks` entry

5. **Test API integration:**
   - Verify that frontend correctly calls backend APIs
   - Test error states (network errors, 409 conflicts, validation errors)
   - Verify SSE connection and event handling

6. **Commit and hand off.**

## Example Handoff

```json
{
  "salientSummary": "Implemented library home screen with grid/list views, sort/filter controls, empty state, and populated state with floating upload button. Added drag-and-drop upload support. Used Svelte 5 runes for state management.",
  "whatWasImplemented": "Library page at frontend/src/routes/+page.svelte with grid/list toggle, sort by recent/duration, filter by status/language, search integration, empty state drop zone with animated waveform, populated state with memo cards, drag-and-drop upload handler, and global search via Cmd+K.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "docker compose exec funasr bash -c 'cd /app/frontend && pnpm check'", "exitCode": 0, "observation": "No type errors" },
      { "command": "docker compose exec funasr bash -c 'cd /app/frontend && pnpm format:check'", "exitCode": 0, "observation": "All files formatted correctly" }
    ],
    "interactiveChecks": [
      { "action": "Navigate to / with empty database", "observed": "Empty state shows drop zone, animated waveform, record CTA, no grid/list toggle" },
      { "action": "Upload a file, wait for completion", "observed": "Library shows memo card with title, duration, status badge. Card is clickable." },
      { "action": "Toggle to list view", "observed": "Layout changes to rows, same data displayed, toggle persists after refresh" },
      { "action": "Sort by duration", "observed": "Cards reorder by duration descending" },
      { "action": "Press Cmd+K", "observed": "Global search overlay opens with focused input" }
    ]
  },
  "tests": {
    "added": []
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature depends on a backend API endpoint that doesn't exist yet
- wavesurfer.js or other library integration requires architectural decisions
- Design system conflicts with existing components
- Requirements are ambiguous about UI behavior
