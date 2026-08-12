"""Versioned SQLite migrations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        title TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        priority INTEGER NOT NULL DEFAULT 0,
        progress REAL NOT NULL DEFAULT 0,
        error TEXT,
        output_path TEXT,
        download_path TEXT,
        format_preference TEXT DEFAULT 'best',
        upscale INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        options_json TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_jobs_status_priority
        ON jobs(status, priority DESC, id ASC);

    CREATE TABLE IF NOT EXISTS download_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL UNIQUE,
        extractor_key TEXT,
        video_id TEXT,
        title TEXT,
        output_path TEXT,
        archived_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    2: """
    ALTER TABLE jobs ADD COLUMN source_width INTEGER;
    ALTER TABLE jobs ADD COLUMN source_height INTEGER;
    """,
}


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not row:
        return 0
    ver = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    return int(ver["v"] if ver else 0)


def migrate(conn: sqlite3.Connection) -> int:
    applied = current_version(conn)
    for version in sorted(MIGRATIONS):
        if version <= applied:
            continue
        conn.executescript(MIGRATIONS[version])
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, _utc_now()),
        )
        conn.commit()
        applied = version
    return applied
