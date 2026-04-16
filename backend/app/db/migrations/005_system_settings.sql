-- Migration 005: System settings overrides (engine config, etc.)
-- Stores runtime-configurable settings that override env var defaults.

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
