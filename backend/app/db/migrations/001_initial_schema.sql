-- Migration 001: Initial schema
-- Creates memos, jobs, segments, memo_speakers tables, FTS5 search index,
-- and triggers to keep FTS5 in sync.

-- ============================================================================
-- memos table
-- ============================================================================
CREATE TABLE IF NOT EXISTS memos (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'upload',
    source_filename TEXT NOT NULL,
    duration_ms INTEGER,
    language_detected TEXT,
    language_override TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    speaker_count INTEGER NOT NULL DEFAULT 0,
    transcript_revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_opened_at TEXT,
    last_edited_at TEXT
);

-- ============================================================================
-- jobs table
-- ============================================================================
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY NOT NULL,
    memo_id TEXT NOT NULL REFERENCES memos(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL DEFAULT 'transcribe',
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT,
    progress REAL NOT NULL DEFAULT 0.0,
    eta_seconds REAL,
    device_used TEXT,
    error_code TEXT,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_memo_id ON jobs(memo_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- ============================================================================
-- segments table
-- ============================================================================
CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY NOT NULL,
    memo_id TEXT NOT NULL REFERENCES memos(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    speaker_key TEXT,
    confidence REAL,
    edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_segments_memo_id ON segments(memo_id);
CREATE INDEX IF NOT EXISTS idx_segments_memo_ordinal ON segments(memo_id, ordinal);

-- ============================================================================
-- memo_speakers table
-- ============================================================================
CREATE TABLE IF NOT EXISTS memo_speakers (
    id TEXT PRIMARY KEY NOT NULL,
    memo_id TEXT NOT NULL REFERENCES memos(id) ON DELETE CASCADE,
    speaker_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_memo_speakers_memo_id ON memo_speakers(memo_id);

-- ============================================================================
-- FTS5 full-text search index
-- VAL-SEARCH-007: FTS5 virtual table for search indexing.
-- Uses content='' (contentless) so we manage inserts/updates/deletes manually
-- via triggers. This keeps the FTS index in sync with memos and segments.
-- ============================================================================
CREATE VIRTUAL TABLE IF NOT EXISTS memos_fts USING fts5(
    title,
    text,
    content='',
    tokenize='unicode61'
);

-- ============================================================================
-- Triggers to keep FTS5 in sync
-- ============================================================================

-- Insert into FTS when a memo is created (index the title)
CREATE TRIGGER IF NOT EXISTS trg_memos_fts_insert
AFTER INSERT ON memos
BEGIN
    INSERT INTO memos_fts(rowid, title, text)
    VALUES (CAST(new.rowid AS INTEGER), new.title, '');
END;

-- Update FTS when a memo title changes
CREATE TRIGGER IF NOT EXISTS trg_memos_fts_update
AFTER UPDATE OF title ON memos
BEGIN
    -- Delete old entry and re-insert with new title
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', CAST(old.rowid AS INTEGER), old.title, '');
    INSERT INTO memos_fts(rowid, title, text)
    VALUES (CAST(new.rowid AS INTEGER), new.title, '');
END;

-- Delete from FTS when a memo is deleted
CREATE TRIGGER IF NOT EXISTS trg_memos_fts_delete
AFTER DELETE ON memos
BEGIN
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', CAST(old.rowid AS INTEGER), old.title, '');
END;

-- Insert into FTS when a segment is created (index the text)
CREATE TRIGGER IF NOT EXISTS trg_segments_fts_insert
AFTER INSERT ON segments
BEGIN
    -- Get the memo's rowid and update the FTS entry with segment text
    -- We use the memo's rowid as the FTS rowid, adding segment text
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', (SELECT rowid FROM memos WHERE id = new.memo_id),
            (SELECT title FROM memos WHERE id = new.memo_id), '');
    INSERT INTO memos_fts(rowid, title, text)
    VALUES ((SELECT rowid FROM memos WHERE id = new.memo_id),
            (SELECT title FROM memos WHERE id = new.memo_id),
            new.text);
END;

-- Update FTS when segment text changes
CREATE TRIGGER IF NOT EXISTS trg_segments_fts_update
AFTER UPDATE OF text ON segments
BEGIN
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', (SELECT rowid FROM memos WHERE id = new.memo_id),
            (SELECT title FROM memos WHERE id = new.memo_id), old.text);
    INSERT INTO memos_fts(rowid, title, text)
    VALUES ((SELECT rowid FROM memos WHERE id = new.memo_id),
            (SELECT title FROM memos WHERE id = new.memo_id),
            new.text);
END;

-- Delete from FTS when a segment is deleted
CREATE TRIGGER IF NOT EXISTS trg_segments_fts_delete
AFTER DELETE ON segments
BEGIN
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', (SELECT rowid FROM memos WHERE id = old.memo_id),
            (SELECT title FROM memos WHERE id = old.memo_id), old.text);
END;
