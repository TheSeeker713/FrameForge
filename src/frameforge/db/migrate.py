"""Versioned SQLite migrations."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path


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
    3: """
    ALTER TABLE jobs ADD COLUMN extractor TEXT;
    """,
    4: """
    CREATE TABLE IF NOT EXISTS library_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        title TEXT,
        source TEXT,
        path TEXT NOT NULL,
        width INTEGER,
        height INTEGER,
        duration REAL,
        thumb_path TEXT,
        date_added TEXT NOT NULL,
        date_modified TEXT,
        is_private INTEGER NOT NULL DEFAULT 0,
        is_favorite INTEGER NOT NULL DEFAULT 0,
        watch_later INTEGER NOT NULL DEFAULT 0,
        primary_collection_id INTEGER
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_library_items_path
        ON library_items(path);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_library_items_job
        ON library_items(job_id) WHERE job_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_library_items_private
        ON library_items(is_private);
    CREATE INDEX IF NOT EXISTS idx_library_items_added
        ON library_items(date_added);

    CREATE TABLE IF NOT EXISTS library_collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        is_seeded INTEGER NOT NULL DEFAULT 0,
        folder_name TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(name, kind)
    );

    CREATE TABLE IF NOT EXISTS library_item_collections (
        item_id INTEGER NOT NULL,
        collection_id INTEGER NOT NULL,
        PRIMARY KEY (item_id, collection_id)
    );

    CREATE TABLE IF NOT EXISTS library_watch_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        import_mode TEXT NOT NULL DEFAULT 'index'
    );
    """,
    5: """
    CREATE TABLE IF NOT EXISTS library_files (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id       INTEGER NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
        role          TEXT    NOT NULL CHECK (role IN ('original','upscaled','linked')),
        path          TEXT    NOT NULL,
        job_id        INTEGER,
        scale         INTEGER,
        model         TEXT,
        width         INTEGER,
        height        INTEGER,
        rotation      INTEGER,
        duration_ms   INTEGER,
        fps           REAL,
        vcodec        TEXT,
        acodec        TEXT,
        pix_fmt       TEXT,
        size_bytes    INTEGER,
        mtime_ns      INTEGER,
        present       INTEGER NOT NULL DEFAULT 1,
        probed_at     TEXT,
        created_at    TEXT    NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_library_files_path ON library_files(path);
    CREATE INDEX IF NOT EXISTS idx_library_files_item ON library_files(item_id);
    CREATE TABLE IF NOT EXISTS library_thumbs (
        file_id     INTEGER PRIMARY KEY REFERENCES library_files(id) ON DELETE CASCADE,
        cache_key   TEXT    NOT NULL,
        thumb_path  TEXT,
        status      TEXT    NOT NULL CHECK (status IN ('ok','miss','pending')),
        error       TEXT,
        attempts    INTEGER NOT NULL DEFAULT 0,
        last_used   TEXT,
        created_at  TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_library_thumbs_key ON library_thumbs(cache_key);
    CREATE INDEX IF NOT EXISTS idx_library_items_title ON library_items(title COLLATE NOCASE);
    """,
}

# Python steps that must stay safe to run again. ALTER is here, not in executescript.
POST_MIGRATE: dict[int, Callable[[sqlite3.Connection], None]] = {}


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not row:
        return 0
    ver = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    return int(ver["v"] if ver else 0)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    if column in _table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _database_file(conn: sqlite3.Connection) -> Path | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None:
        return None
    raw = row["file"] if isinstance(row, sqlite3.Row) else row[2]
    if not raw:
        return None
    return Path(str(raw))


def _backup_before_v5(conn: sqlite3.Connection) -> None:
    """Copy the live database once, before version 5 changes it."""
    path = _database_file(conn)
    if path is None or not path.is_file():
        return
    dest = Path(str(path) + ".bak-v4")
    if dest.exists():
        return
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass
    shutil.copy2(path, dest)


def _post_migrate_5(conn: sqlite3.Connection) -> None:
    for column, decl in (
        ("source_url", "TEXT"),
        ("source_site", "TEXT"),
        ("primary_file_id", "INTEGER"),
        ("duration_ms", "INTEGER"),
        ("file_size", "INTEGER"),
    ):
        _add_column(conn, "library_items", column, decl)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_library_items_site ON library_items(source_site)"
    )
    from frameforge.library.versions import backfill_version_rows

    backfill_version_rows(conn)


POST_MIGRATE[5] = _post_migrate_5


def migrate(conn: sqlite3.Connection) -> int:
    applied = current_version(conn)
    for version in sorted(MIGRATIONS):
        if version <= applied:
            continue
        if version == 5:
            _backup_before_v5(conn)
        conn.executescript(MIGRATIONS[version])
        hook = POST_MIGRATE.get(version)
        if hook is not None:
            hook(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, _utc_now()),
        )
        conn.commit()
        applied = version
    return applied
