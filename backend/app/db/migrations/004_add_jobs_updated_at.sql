-- Migration 004: Add updated_at column to jobs table

ALTER TABLE jobs ADD COLUMN updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
