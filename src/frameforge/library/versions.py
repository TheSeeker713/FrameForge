"""One library card, several files. The video on disk is never moved.

The primary file is the best version that is still present: the tallest
upscale, otherwise the original, otherwise a linked file. ``library_items.path``
always matches that file so older callers keep working.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from frameforge.db.repository import utc_now
from frameforge.library.models import LibraryFile

_SCALE_RE = re.compile(r"(?:^|[_\-.])x([24])(?:[_\-.]|$)", re.I)
_ROLE_RANK = {"upscaled": 0, "original": 1, "linked": 2}


def http_url(url: str | None) -> str | None:
    """Return the URL when it is http or https. Anything else is dropped."""
    if not url:
        return None
    text = str(url).strip()
    lowered = text.lower()
    if lowered.startswith("https://") or lowered.startswith("http://"):
        return text
    return None


def site_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        return host[4:]
    return host


def parse_scale(name: str, options: dict[str, Any] | None = None) -> int | None:
    if options:
        for key in ("scale", "upscale_scale"):
            raw = options.get(key)
            if raw in (2, 4, "2", "4"):
                return int(raw)
    match = _SCALE_RE.search(name)
    if match:
        return int(match.group(1))
    return None


def parse_model(options: dict[str, Any] | None) -> str | None:
    if not options:
        return None
    for key in ("model", "upscale_model", "onnx_model"):
        raw = options.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def best_file(files: list[LibraryFile]) -> LibraryFile | None:
    present = [row for row in files if row.present]
    pool = present or list(files)
    if not pool:
        return None
    upscales = [row for row in pool if row.role == "upscaled" and row.present]
    if upscales:
        return max(upscales, key=lambda row: (row.height or 0, row.scale or 0, row.id))
    return min(pool, key=lambda row: (_ROLE_RANK.get(row.role, 9), row.id))


def remember_source(store: Any, item_id: int, url: str | None) -> None:
    """Store an http(s) source URL. Other schemes are ignored."""
    clean = http_url(url)
    if not clean:
        return
    store.conn.execute(
        "UPDATE library_items SET source_url = ?, source_site = ?, date_modified = ? WHERE id = ?",
        (clean, site_host(clean), utc_now(), item_id),
    )
    store.conn.commit()


def attach_upscale_output(
    store: Any,
    job: Any,
    output_path: str | Path,
    scale: int | None = None,
    model: str | None = None,
) -> LibraryFile | None:
    """Add an upscale file to the download's card. The file stays where it is."""
    output = Path(output_path)
    try:
        if not output.is_file():
            return None
    except OSError:
        return None
    item = store.get_by_job_id(getattr(job, "id", None)) if getattr(job, "id", None) else None
    download = getattr(job, "download_path", None)
    if item is None and download:
        item = store.get_by_path(download)
    if item is None:
        return None
    existing = store.get_file_by_path(output)
    if existing is not None:
        return existing
    options = job.options() if hasattr(job, "options") else None
    if scale is None:
        scale = parse_scale(output.name, options)
    if model is None:
        model = parse_model(options)
    return store.add_file(
        item.id,
        role="upscaled",
        path=output,
        job_id=getattr(job, "id", None),
        scale=scale,
        model=model,
    )


def mark_missing_files(store: Any) -> int:
    """Flag file rows whose path is gone. Does not delete the row or the card."""
    changed = 0
    rows = store.conn.execute("SELECT id, path, present FROM library_files").fetchall()
    for row in rows:
        try:
            exists = Path(row["path"]).is_file()
        except OSError:
            exists = False
        if exists and not row["present"]:
            store.set_file_probe(int(row["id"]), present=1)
            changed += 1
        elif not exists and row["present"]:
            store.mark_file_missing(int(row["id"]))
            changed += 1
    return changed


def sync_primary(store: Any, item_id: int) -> None:
    """Point the item row at the best present file. Does not touch the file."""
    files = store.list_files(item_id)
    chosen = best_file(files)
    if chosen is None:
        return
    now = utc_now()
    store.conn.execute(
        """
        UPDATE library_items
        SET path = ?, primary_file_id = ?, width = ?, height = ?,
            duration_ms = ?, file_size = ?, date_modified = ?
        WHERE id = ?
        """,
        (
            chosen.path,
            chosen.id,
            chosen.width,
            chosen.height,
            chosen.duration_ms,
            chosen.size_bytes,
            now,
            item_id,
        ),
    )
    store.conn.commit()


def backfill_version_rows(conn: sqlite3.Connection) -> None:
    """Fill file rows for items that already exist. No ffprobe."""
    now = utc_now()
    items = conn.execute("SELECT * FROM library_items").fetchall()
    for item in items:
        item_id = int(item["id"])
        path = str(item["path"])
        job_id = item["job_id"]
        role = "original" if job_id is not None else "linked"
        file_id = _ensure_file(
            conn,
            item_id=item_id,
            role=role,
            path=path,
            job_id=int(job_id) if job_id is not None else None,
            scale=None,
            model=None,
            now=now,
        )
        _copy_thumb(conn, file_id, item["thumb_path"], now)
        if job_id is None:
            _set_primary(conn, item_id, file_id, path, now)
            continue
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (int(job_id),)).fetchone()
        if job is None:
            _set_primary(conn, item_id, file_id, path, now)
            continue
        url = http_url(job["url"])
        if url:
            conn.execute(
                "UPDATE library_items SET source_url = ?, source_site = ? WHERE id = ?",
                (url, site_host(url), item_id),
            )
        options = _options(job["options_json"])
        output = job["output_path"]
        download = job["download_path"]
        if output and output != download and Path(str(output)).is_file():
            up_id = _ensure_file(
                conn,
                item_id=item_id,
                role="upscaled",
                path=str(Path(output).resolve()),
                job_id=int(job_id),
                scale=parse_scale(Path(str(output)).name, options),
                model=parse_model(options),
                now=now,
            )
            up_row = conn.execute("SELECT * FROM library_files WHERE id = ?", (up_id,)).fetchone()
            orig = conn.execute("SELECT * FROM library_files WHERE id = ?", (file_id,)).fetchone()
            chosen = best_file([LibraryFile.from_row(orig), LibraryFile.from_row(up_row)])
            if chosen is not None:
                file_id = chosen.id
                path = chosen.path
        _set_primary(conn, item_id, file_id, path, now)
    conn.commit()


def _options(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ensure_file(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    role: str,
    path: str,
    job_id: int | None,
    scale: int | None,
    model: str | None,
    now: str,
) -> int:
    dest = str(Path(path).resolve()) if Path(path).exists() else path
    row = conn.execute("SELECT id FROM library_files WHERE path = ?", (dest,)).fetchone()
    if row is not None:
        return int(row["id"])
    size = None
    mtime = None
    present = 0
    target = Path(dest)
    if target.is_file():
        present = 1
        try:
            stat = target.stat()
            size = int(stat.st_size)
            mtime = int(stat.st_mtime_ns)
        except OSError:
            present = 0
    cur = conn.execute(
        """
        INSERT INTO library_files(
            item_id, role, path, job_id, scale, model, size_bytes, mtime_ns,
            present, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, role, dest, job_id, scale, model, size, mtime, present, now),
    )
    return int(cur.lastrowid)


def _copy_thumb(conn: sqlite3.Connection, file_id: int, thumb_path: str | None, now: str) -> None:
    if not thumb_path or not Path(str(thumb_path)).is_file():
        return
    existing = conn.execute(
        "SELECT file_id FROM library_thumbs WHERE file_id = ?", (file_id,)
    ).fetchone()
    if existing is not None:
        return
    key = hashlib.sha1(f"legacy|{thumb_path}".encode()).hexdigest()
    conn.execute(
        """
        INSERT INTO library_thumbs(file_id, cache_key, thumb_path, status, attempts, created_at)
        VALUES (?, ?, ?, 'ok', 0, ?)
        """,
        (file_id, key, str(thumb_path), now),
    )


def _set_primary(conn: sqlite3.Connection, item_id: int, file_id: int, path: str, now: str) -> None:
    file_row = conn.execute("SELECT * FROM library_files WHERE id = ?", (file_id,)).fetchone()
    conn.execute(
        """
        UPDATE library_items
        SET path = ?, primary_file_id = ?, file_size = ?, date_modified = ?
        WHERE id = ?
        """,
        (
            path,
            file_id,
            file_row["size_bytes"] if file_row is not None else None,
            now,
            item_id,
        ),
    )
