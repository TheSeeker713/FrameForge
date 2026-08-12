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
TERMINAL_STATUSES = ("completed", "failed", "cancelled")
PAUSED_STATUS = "paused"
HOLDING_STATUSES = (PAUSED_STATUS,)


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
    source_width: int | None = None
    source_height: int | None = None
    extractor: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        keys = set(row.keys())
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
            source_width=row["source_width"] if "source_width" in keys else None,
            source_height=row["source_height"] if "source_height" in keys else None,
            extractor=row["extractor"] if "extractor" in keys else None,
        )

    def options(self) -> dict[str, Any]:
        if not self.options_json:
            return {}
        return json.loads(self.options_json)

    @property
    def upscale_recommended(self) -> bool:
        """True when source height is known and ≤ 720p (Tier 3 recommendation)."""
        from frameforge.upscale.guards import is_upscale_recommended

        return is_upscale_recommended(self.source_height)

    @property
    def upscale_blocked(self) -> bool:
        from frameforge.upscale.guards import is_upscale_blocked

        return is_upscale_blocked(self.source_height)

    @property
    def thumbnail_path(self) -> str | None:
        path = self.options().get("thumbnail_path")
        return str(path) if path else None

    @property
    def playlist_id(self) -> str | None:
        pid = self.options().get("playlist_id")
        return str(pid) if pid else None

    @property
    def playlist_index(self) -> int | None:
        idx = self.options().get("playlist_index")
        if idx is None:
            return None
        try:
            return int(idx)
        except (TypeError, ValueError):
            return None

    @property
    def playlist_badge(self) -> str:
        if not self.playlist_id and self.playlist_index is None:
            return ""
        if self.playlist_index is not None:
            return f"PL {self.playlist_index}"
        return "PL"


class JobRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = connect(self.db_path)
        self._lock = __import__("threading").RLock()
        migrate(self.conn)

    def close(self) -> None:
        with self._lock:
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
        extractor: str | None = None,
    ) -> Job:
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO jobs(
                url, title, status, priority, progress, format_preference, upscale,
                created_at, updated_at, options_json, extractor
            ) VALUES (?, ?, 'pending', ?, 0, ?, ?, ?, ?, ?, ?)
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
                extractor,
            ),
        )
        self.conn.commit()
        return self.get(int(cur.lastrowid))

    def get(self, job_id: int) -> Job:
        with self._lock:
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

    def list_jobs_for_playlist(self, playlist_id: str) -> list[Job]:
        rows = self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE json_extract(options_json, '$.playlist_id') = ?
            ORDER BY CAST(json_extract(options_json, '$.playlist_index') AS INTEGER) ASC, id ASC
            """,
            (playlist_id,),
        ).fetchall()
        return [Job.from_row(r) for r in rows]

    def list_history(
        self,
        *,
        status: str | None = None,
        search: str | None = None,
        include_hidden: bool = False,
    ) -> list[Job]:
        """Terminal jobs (completed/failed/cancelled) for the History view.

        *status*: ``None`` = all terminal; or one of completed/failed/cancelled.
        *search*: case-insensitive substring match on title, url, or extractor.
        Does not change ``list_jobs`` / claim behavior for the active queue.
        """
        if status is not None and status not in TERMINAL_STATUSES:
            raise ValueError(f"history status must be one of {TERMINAL_STATUSES}, got {status!r}")
        statuses = (status,) if status else TERMINAL_STATUSES
        placeholders = ",".join("?" * len(statuses))
        sql = f"SELECT * FROM jobs WHERE status IN ({placeholders})"
        params: list[Any] = list(statuses)
        needle = (search or "").strip()
        if needle:
            like = f"%{needle}%"
            sql += " AND (IFNULL(title,'') LIKE ? OR url LIKE ? OR IFNULL(extractor,'') LIKE ?)"
            params.extend([like, like, like])
        sql += " ORDER BY COALESCE(finished_at, updated_at) DESC, id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        jobs = [Job.from_row(r) for r in rows]
        if not include_hidden:
            jobs = [j for j in jobs if not j.options().get("history_hidden")]
        return jobs

    def hide_from_history(self, job_ids: list[int] | tuple[int, ...]) -> int:
        """Soft-hide terminal jobs from History (non-destructive; rows stay in SQLite)."""
        n = 0
        for jid in job_ids:
            job = self.get(int(jid))
            if job.status not in TERMINAL_STATUSES:
                continue
            self.merge_options(int(jid), {"history_hidden": True})
            n += 1
        return n

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
        if status == PAUSED_STATUS:
            finished = None
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

    def merge_options(self, job_id: int, patch: dict[str, Any]) -> Job:
        """Shallow-merge keys into the job's options_json."""
        job = self.get(job_id)
        opts = job.options()
        opts.update(patch)
        self.conn.execute(
            "UPDATE jobs SET options_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(opts), utc_now(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def update_progress(
        self,
        job_id: int,
        progress: float,
        *,
        speed_bps: float | None = None,
        eta_seconds: float | None = None,
        speed_str: str | None = None,
        eta_str: str | None = None,
    ) -> None:
        job = self.get(job_id)
        opts = job.options()
        if speed_bps is not None:
            opts["speed_bps"] = speed_bps
        if eta_seconds is not None:
            opts["eta_seconds"] = eta_seconds
        if speed_str is not None:
            opts["speed_str"] = speed_str
        if eta_str is not None:
            opts["eta_str"] = eta_str
        if progress >= 100 or job.status in ("completed", "failed", "cancelled"):
            opts.pop("speed_bps", None)
            opts.pop("eta_seconds", None)
            opts["speed_str"] = "—"
            opts["eta_str"] = "—"
        self.conn.execute(
            """
            UPDATE jobs SET progress = ?, options_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (progress, json.dumps(opts) if opts else None, utc_now(), job_id),
        )
        self.conn.commit()

    def clear_live_progress(self, job_id: int) -> None:
        job = self.get(job_id)
        opts = job.options()
        opts.pop("speed_bps", None)
        opts.pop("eta_seconds", None)
        opts["speed_str"] = "—"
        opts["eta_str"] = "—"
        self.conn.execute(
            "UPDATE jobs SET options_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(opts), utc_now(), job_id),
        )
        self.conn.commit()

    def set_paths(
        self,
        job_id: int,
        *,
        download_path: str | None = None,
        output_path: str | None = None,
    ) -> Job:
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

    def set_source_resolution(
        self,
        job_id: int,
        width: int | None,
        height: int | None,
    ) -> Job:
        self.conn.execute(
            """
            UPDATE jobs
            SET source_width = ?, source_height = ?, updated_at = ?
            WHERE id = ?
            """,
            (width, height, utc_now(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def probe_and_store_resolution(self, job_id: int, path: str | Path | None = None) -> Job:
        """Probe video size for a job artifact; never raises — unknown stays NULL."""
        job = self.get(job_id)
        src = path or job.download_path or job.output_path
        if not src or not Path(src).exists():
            return self.set_source_resolution(job_id, None, None)
        try:
            from frameforge.upscale.ffmpeg_utils import video_size

            width, height = video_size(Path(src))
            return self.set_source_resolution(job_id, int(width), int(height))
        except Exception:
            return self.set_source_resolution(job_id, None, None)

    def set_title(self, job_id: int, title: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET title = ?, updated_at = ? WHERE id = ?",
            (title, utc_now(), job_id),
        )
        self.conn.commit()

    def set_extractor(self, job_id: int, extractor: str | None) -> Job:
        self.conn.execute(
            "UPDATE jobs SET extractor = ?, updated_at = ? WHERE id = ?",
            (extractor, utc_now(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def set_priority(self, job_id: int, priority: int) -> Job:
        self.conn.execute(
            "UPDATE jobs SET priority = ?, updated_at = ? WHERE id = ?",
            (priority, utc_now(), job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def queue_for_upscale(self, job_id: int) -> Job:
        """Move a completed job with a local download artifact into the upscale stage.

        Sets upscale=1 and status=download_completed so the sequential worker will
        run the upscale handler without requiring the original enqueue flag.
        """
        from pathlib import Path

        job = self.get(job_id)
        if job.status != "completed":
            raise ValueError(
                f"Job {job_id} status is '{job.status}' (need completed to upscale)"
            )
        src = job.download_path or job.output_path
        if not src or not Path(src).exists():
            raise ValueError(f"Job {job_id} has no valid download_path for upscale")
        if job.source_height is None:
            self.probe_and_store_resolution(job_id, src)
        now = utc_now()
        self.conn.execute(
            """
            UPDATE jobs
            SET upscale = 1,
                status = 'download_completed',
                progress = 0,
                error = NULL,
                finished_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (now, job_id),
        )
        self.conn.commit()
        return self.get(job_id)

    def cancel(self, job_id: int) -> Job:
        return self.update_status(job_id, "cancelled", progress=0)

    def pause(self, job_id: int) -> Job:
        """Mark an active job paused. Keeps progress and paths; does not fail or cancel."""
        job = self.get(job_id)
        if job.status == PAUSED_STATUS:
            return job
        if job.status not in INTERRUPTIBLE_STATUSES:
            raise ValueError(
                f"Job {job_id} status is '{job.status}' (need downloading/upscaling to pause)"
            )
        self.merge_options(
            job_id,
            {"paused": True, "paused_from": job.status},
        )
        return self.update_status(job_id, PAUSED_STATUS)

    def resume_paused(self, job_id: int) -> Job:
        """Return a paused job to a claimable stage (download pending or upscale chain)."""
        job = self.get(job_id)
        if job.status != PAUSED_STATUS:
            raise ValueError(f"Job {job_id} status is '{job.status}' (need paused to resume)")
        from_stage = job.options().get("paused_from") or "downloading"
        self.merge_options(job_id, {"paused": False, "continue_download": True})
        if from_stage == "upscaling":
            now = utc_now()
            self.conn.execute(
                """
                UPDATE jobs
                SET status = 'download_completed', upscale = 1, error = NULL,
                    finished_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
            self.conn.commit()
            return self.get(job_id)
        return self.update_status(job_id, "pending", error=None)

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
        """Reset interrupted downloading/upscaling jobs to pending for retry.

        Startup / process-restart policy (unchanged): active stages become
        ``pending`` with error ``Recovered after interrupted run`` so the user
        can start them again. In-process handler exceptions are failed by the
        worker instead (they are not treated as a crash restart).
        """
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
