"""Job repository over SQLite."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from frameforge.db.connection import connect
from frameforge.db.migrate import migrate

ACTIVE_DOWNLOAD_STATUSES = ("downloading",)
INTERRUPTIBLE_STATUSES = ("downloading", "upscaling")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Job:
    id: int
    url: str
    title: str | None
    status: str
    priority: int
    progress: float
    error: str | None
    output_path: str | None
    download_path: str | None
    format_preference: str | None
    upscale: bool
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    options_json: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        return cls(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            status=row["status"],
            priority=row["priority"],
            progress=float(row["progress"]),
            error=row["error"],
            output_path=row["output_path"],
            download_path=row["download_path"],
            format_preference=row["format_preference"],
            upscale=bool(row["upscale"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            options_json=row["options_json"],
        )

    def options(self) -> dict[str, Any]:
        if not self.options_json:
            return {}
        return json.loads(self.options_json)


class JobRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = connect(self.db_path)
        migrate(self.conn)

    def close(self) -> None:
        self.conn.close()

    def enqueue(
        self,
        url: str,
        *,
        title: str | None = None,
        priority: int = 0,
        format_preference: str = "best",
        upscale: bool = False,
        options: dict[str, Any] | None = None,
    ) -> Job:
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO jobs(
                url, title, status, priority, progress, format_preference, upscale,
                created_at, updated_at, options_json
            ) VALUES (?, ?, 'pending', ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                url,
                title,
                priority,
                format_preference,
                1 if upscale else 0,
                now,
                now,
                json.dumps(options) if options else None,
            ),
        )
        self.conn.commit()
        return self.get(int(cur.lastrowid))

    def get(self, job_id: int) -> Job:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise KeyError(f"job {job_id} not found")
        return Job.from_row(row)

    def list_jobs(self, status: str | None = None) -> list[Job]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC, id ASC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jobs ORDER BY priority DESC, id ASC"
            ).fetchall()
        return [Job.from_row(r) for r in rows]

    def count_by_status(self, status: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE status = ?", (status,)
        ).fetchone()
        return int(row["c"])

    def update_status(
        self,
        job_id: int,
        status: str,
        *,
        error: str | None = None,
        progress: float | None = None,
    ) -> Job:
        now = utc_now()
        job = self.get(job_id)
        started = job.started_at
        finished = job.finished_at
        if status in ("downloading", "upscaling") and not started:
            started = now
        if status in ("completed", "failed", "cancelled"):
            finished = now
        prog = job.progress if progress is None else progress
        self.conn.execute(
            """
            UPDATE jobs
            SET status = ?, error = ?, progress = ?, updated_at = ?,
                started_at = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, error, prog, now, started, finished, job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def update_progress(self, job_id: int, progress: float) -> None:
        self.conn.execute(
            "UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?",
            (progress, utc_now(), job_id),
        )
        self.conn.commit()

    def set_paths(
        self,
        job_id: int,
        *,
        download_path: str | None = None,
        output_path: str | None = None,
    ) -> Job:
        job = self.get(job_id)
        self.conn.execute(
            """
            UPDATE jobs
            SET download_path = COALESCE(?, download_path),
                output_path = COALESCE(?, output_path),
                updated_at = ?
            WHERE id = ?
            """,
            (download_path, output_path, utc_now(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def set_title(self, job_id: int, title: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET title = ?, updated_at = ? WHERE id = ?",
            (title, utc_now(), job_id),
        )
        self.conn.commit()

    def set_priority(self, job_id: int, priority: int) -> Job:
        self.conn.execute(
            "UPDATE jobs SET priority = ?, updated_at = ? WHERE id = ?",
            (priority, utc_now(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def cancel(self, job_id: int) -> Job:
        return self.update_status(job_id, "cancelled", progress=0)

    def claim_next_pending(self, job_ids: list[int] | None = None) -> Job | None:
        """Atomically claim the highest-priority pending job for download stage.

        Enforces sequential invariant: refuse if any job is already downloading.
        If job_ids is provided, only those IDs are eligible.
        """
        if job_ids is not None and len(job_ids) == 0:
            return None
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            active = self.conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status = 'downloading'"
            ).fetchone()
            if int(active["c"]) > 0:
                self.conn.execute("ROLLBACK")
                return None
            # Also block if another stage is actively running under single-worker design
            busy = self.conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status IN ('downloading', 'upscaling')"
            ).fetchone()
            if int(busy["c"]) > 0:
                self.conn.execute("ROLLBACK")
                return None
            if job_ids is None:
                row = self.conn.execute(
                    """
                    SELECT id FROM jobs
                    WHERE status = 'pending'
                    ORDER BY priority DESC, id ASC
                    LIMIT 1
                    """
                ).fetchone()
            else:
                placeholders = ",".join("?" * len(job_ids))
                row = self.conn.execute(
                    f"""
                    SELECT id FROM jobs
                    WHERE status = 'pending' AND id IN ({placeholders})
                    ORDER BY priority DESC, id ASC
                    LIMIT 1
                    """,
                    tuple(job_ids),
                ).fetchone()
            if not row:
                self.conn.execute("ROLLBACK")
                return None
            now = utc_now()
            self.conn.execute(
                """
                UPDATE jobs
                SET status = 'downloading', progress = 0, updated_at = ?,
                    started_at = COALESCE(started_at, ?), error = NULL
                WHERE id = ?
                """,
                (now, now, row["id"]),
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get(int(row["id"]))
    def recover_interrupted(self) -> list[int]:
        """Reset interrupted downloading/upscaling jobs to pending for retry."""
        rows = self.conn.execute(
            "SELECT id FROM jobs WHERE status IN ('downloading', 'upscaling')"
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if not ids:
            return []
        now = utc_now()
        self.conn.execute(
            """
            UPDATE jobs
            SET status = 'pending', error = 'Recovered after interrupted run',
                progress = 0, updated_at = ?
            WHERE status IN ('downloading', 'upscaling')
            """,
            (now,),
        )
        self.conn.commit()
        return ids

    def url_in_queue(self, url: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM jobs
            WHERE url = ? AND status NOT IN ('cancelled')
            LIMIT 1
            """,
            (url,),
        ).fetchone()
        return row is not None

    def add_archive(
        self,
        url: str,
        *,
        title: str | None = None,
        output_path: str | None = None,
        extractor_key: str | None = None,
        video_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO download_archive(url, extractor_key, video_id, title, output_path, archived_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                output_path = excluded.output_path,
                archived_at = excluded.archived_at
            """,
            (url, extractor_key, video_id, title, output_path, utc_now()),
        )
        self.conn.commit()

    def archive_lookup(self, url: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM download_archive WHERE url = ?", (url,)
        ).fetchone()

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
