"""Clear the download queue. Does not delete videos, cookies, or the app home."""

from __future__ import annotations

import sqlite3

from frameforge.db.repository import JobRepository

ACTIVE_STATUSES = ("downloading", "upscaling", "converting")


class QueueResetRefused(RuntimeError):
    """A download, upscale, or convert is in progress."""


def reset_queue(repo: JobRepository) -> int:
    """Delete every job and download-archive row. Returns how many jobs were removed.

    Library rows, settings, and files on disk are left alone. Refuses while a
    job is downloading, upscaling, or converting.
    """
    conn = repo.conn
    placeholders = ",".join("?" * len(ACTIVE_STATUSES))
    active = conn.execute(
        f"SELECT COUNT(*) AS c FROM jobs WHERE status IN ({placeholders})",
        ACTIVE_STATUSES,
    ).fetchone()
    if int(active["c"]) > 0:
        raise QueueResetRefused(
            "A download is in progress. The queue was not reset."
        )
    count = int(conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"])
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM download_archive")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('jobs', 'download_archive')"
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass
    return count
