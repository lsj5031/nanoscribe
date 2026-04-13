# SQLite Schema and Migrations

## Overview

The database uses SQLite with WAL mode and foreign key enforcement. Migrations are hand-rolled SQL files in `backend/app/db/migrations/`, applied in sorted order by the migration runner in `backend/app/db/migrate.py`.

## Schema (Migration 001)

### Tables

- **memos**: Core entity for audio memos. PK is TEXT (UUID). Has `status` (default 'queued'), `transcript_revision` (default 0), `speaker_count` (default 0). Timestamps auto-populated via `strftime`.
- **jobs**: Processing pipeline state. FK to `memos(id)` with ON DELETE CASCADE. Has `progress` (REAL, default 0.0), `attempt_count` (NOT NULL, default 1), `error_code`/`error_message` for failure tracking.
- **segments**: Transcript segments. FK to `memos(id)` with ON DELETE CASCADE. Has `ordinal`, `start_ms`, `end_ms`, `text`, `speaker_key`, `confidence`, `edited` (default 0/FALSE).
- **memo_speakers**: Per-memo speaker labels. FK to `memos(id)` with ON DELETE CASCADE. Has `speaker_key`, `display_name`, `color`.
- **memos_fts**: FTS5 virtual table with `content=''` (contentless). Indexes `title` and `text` using `unicode61` tokenizer.
- **_migrations**: Tracks applied migrations (`name` PK + `applied_at`).

### Indexes

- `idx_jobs_memo_id` on `jobs(memo_id)`
- `idx_jobs_status` on `jobs(status)`
- `idx_segments_memo_id` on `segments(memo_id)`
- `idx_segments_memo_ordinal` on `segments(memo_id, ordinal)`
- `idx_memo_speakers_memo_id` on `memo_speakers(memo_id)`

### FTS5 Sync Triggers

Six triggers keep `memos_fts` in sync:
- `trg_memos_fts_insert/update/delete`: Sync memo title changes
- `trg_segments_fts_insert/update/delete`: Sync segment text changes

Note: FTS5 uses `content=''` (contentless), so delete operations use the `INSERT INTO memos_fts(memos_fts, rowid, ...) VALUES ('delete', ...)` pattern.

## How to Add Migrations

1. Create a new numbered `.sql` file in `backend/app/db/migrations/` (e.g., `002_add_column.sql`)
2. Use `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, etc. for idempotency
3. The migration runner automatically picks up new files and applies them in order

## Running Migrations

```python
from app.db.migrate import run_migrations
run_migrations()  # Uses default path from NANOSCRIBE_DATA_DIR
# or
run_migrations("/path/to/custom.db")
```

Or via command line:
```bash
cd /app/backend && python -m app.db.migrate
```
