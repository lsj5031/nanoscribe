-- Migration 002: Fix FTS5 segment triggers
-- The original triggers used the memo's rowid as the FTS rowid for segments,
-- causing only the LAST segment per memo to be searchable. Fix: each segment
-- gets its own FTS entry using the segment's own rowid.

-- Drop the buggy segment triggers
DROP TRIGGER IF EXISTS trg_segments_fts_insert;
DROP TRIGGER IF EXISTS trg_segments_fts_update;
DROP TRIGGER IF EXISTS trg_segments_fts_delete;

-- Insert into FTS when a segment is created (index the segment text)
-- Each segment gets its own FTS row using the segment's rowid.
-- This allows ALL segments per memo to be independently searchable.
CREATE TRIGGER IF NOT EXISTS trg_segments_fts_insert
AFTER INSERT ON segments
BEGIN
    INSERT INTO memos_fts(rowid, title, text)
    VALUES (CAST(new.rowid AS INTEGER), '', new.text);
END;

-- Update FTS when segment text changes
CREATE TRIGGER IF NOT EXISTS trg_segments_fts_update
AFTER UPDATE OF text ON segments
BEGIN
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', CAST(old.rowid AS INTEGER), '', old.text);
    INSERT INTO memos_fts(rowid, title, text)
    VALUES (CAST(new.rowid AS INTEGER), '', new.text);
END;

-- Delete from FTS when a segment is deleted
CREATE TRIGGER IF NOT EXISTS trg_segments_fts_delete
AFTER DELETE ON segments
BEGIN
    INSERT INTO memos_fts(memos_fts, rowid, title, text)
    VALUES ('delete', CAST(old.rowid AS INTEGER), '', old.text);
END;
