-- Migration 003: Add hotwords and enable_diarization columns to jobs table

ALTER TABLE jobs ADD COLUMN hotwords TEXT;
ALTER TABLE jobs ADD COLUMN enable_diarization INTEGER NOT NULL DEFAULT 0;
