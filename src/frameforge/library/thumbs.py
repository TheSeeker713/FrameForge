"""Library thumbnail cache. Extraction never runs on the UI thread.

Each file has its own key, so a download and its upscale do not share a still.
A file replaced in place gets a new key. A miss stays a miss until the key
changes or the user asks for a new still.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from frameforge.library.models import LibraryItem
from frameforge.library.store import LibraryStore

log = logging.getLogger(__name__)

_MAX_BYTES = 2 * 1024 * 1024 * 1024
_LUMA_FLOOR = 16.0


def cache_key(path: str | Path, size_bytes: int, mtime_ns: int) -> str:
    abs_path = str(Path(path).resolve()) if Path(path).exists() else str(Path(path))
    raw = f"{abs_path}|{int(size_bytes)}|{int(mtime_ns)}|v1"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def seek_time(duration: float | None) -> float:
    """Seconds to seek. Unknown duration uses 1s. Clips under 1s start at 0."""
    if duration is None:
        return 1.0
    if duration < 1.0:
        return 0.0
    return min(float(duration) * 0.10, 5.0)


def thumb_file(key: str) -> Path:
    from frameforge.paths import thumbnails_dir

    return thumbnails_dir() / "library" / key[:2] / f"{key}.jpg"


def file_stat_key(path: str | Path) -> tuple[str, int, int] | None:
    target = Path(path)
    try:
        if not target.is_file():
            return None
        stat = target.stat()
    except OSError:
        return None
    return cache_key(target, int(stat.st_size), int(stat.st_mtime_ns)), int(stat.st_size), int(stat.st_mtime_ns)


def ffmpeg_still_argv(ffmpeg: str, src: Path, dest: Path, seek: float) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-ss",
        f"{seek:.3f}",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        "thumbnail=24,scale=480:-2:flags=bicubic",
        "-frames:v",
        "1",
        "-q:v",
        "4",
        str(dest),
    ]


def mean_luma(path: Path) -> float | None:
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as img:
            return float(ImageStat.Stat(img.convert("L")).mean[0])
    except Exception:  # noqa: BLE001
        return None


def extract_library_thumb(
    src: Path,
    dest: Path,
    *,
    duration: float | None,
    ffmpeg: str,
    run: Callable[[list[str]], int] | None = None,
    luma: Callable[[Path], float | None] | None = None,
) -> Path | None:
    """Write one JPEG. Never raises. Retries a black frame when duration is known."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    runner = run or _default_run
    measure = luma or mean_luma
    first = seek_time(duration)
    attempts = [first]
    if duration is not None and duration >= 1.0:
        attempts.extend([duration * 0.25, duration * 0.50])
    if 0.0 not in attempts:
        attempts.append(0.0)
    best_path: Path | None = None
    best_luma = -1.0
    for index, seek in enumerate(attempts):
        out = dest if index == 0 else dest.with_name(f"{dest.stem}_try{index}.jpg")
        try:
            code = runner(ffmpeg_still_argv(ffmpeg, src, out, seek))
        except Exception:  # noqa: BLE001
            log.exception("Thumbnail extract failed for %s", src)
            return best_path
        if code != 0 or not out.is_file() or out.stat().st_size <= 32:
            if index == 0 and seek != 0.0:
                continue
            continue
        score = measure(out)
        if score is None:
            score = _LUMA_FLOOR
        if score > best_luma:
            best_luma = score
            if out != dest:
                dest.write_bytes(out.read_bytes())
            best_path = dest
        if score >= _LUMA_FLOOR and index == 0:
            break
        if score >= _LUMA_FLOOR and best_path is not None:
            break
    for extra in dest.parent.glob(f"{dest.stem}_try*.jpg"):
        try:
            extra.unlink()
        except OSError:
            pass
    return best_path if best_path is not None and best_path.is_file() else None


def _default_run(argv: list[str]) -> int:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(  # noqa: S603
        argv,
        capture_output=True,
        timeout=20,
        check=False,
        creationflags=flags,
    )
    return int(proc.returncode)


def save_thumb_row(
    store: LibraryStore,
    file_id: int,
    *,
    cache_key_value: str,
    status: str,
    thumb_path: str | None = None,
    error: str | None = None,
) -> None:
    from frameforge.db.repository import utc_now

    now = utc_now()
    existing = store.get_thumb(file_id)
    attempts = 0 if existing is None else int(existing.attempts)
    if status == "miss":
        attempts += 1
    if existing is None:
        store.conn.execute(
            """
            INSERT INTO library_thumbs(
                file_id, cache_key, thumb_path, status, error, attempts, last_used, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, cache_key_value, thumb_path, status, error, attempts, now, now),
        )
    else:
        store.conn.execute(
            """
            UPDATE library_thumbs
            SET cache_key = ?, thumb_path = ?, status = ?, error = ?, attempts = ?, last_used = ?
            WHERE file_id = ?
            """,
            (cache_key_value, thumb_path, status, error, attempts, now, file_id),
        )
    store.conn.commit()


def thumb_is_current(store: LibraryStore, file_id: int, key: str) -> bool:
    row = store.get_thumb(file_id)
    if row is None or row.cache_key != key:
        return False
    if row.status == "miss":
        return True
    return bool(row.thumb_path and Path(row.thumb_path).is_file())


def prune_thumb_cache(store: LibraryStore, *, max_bytes: int = _MAX_BYTES) -> int:
    """Drop the least recently used stills past the cap, then unreferenced files."""
    from frameforge.paths import thumbnails_dir

    root = thumbnails_dir() / "library"
    if not root.is_dir():
        return 0
    rows = store.conn.execute(
        "SELECT cache_key, thumb_path, last_used FROM library_thumbs WHERE thumb_path IS NOT NULL"
    ).fetchall()
    known: dict[str, str | None] = {}
    for row in rows:
        path = row["thumb_path"]
        if path:
            known[str(Path(path).resolve()).lower()] = row["last_used"]
    files: list[tuple[str, Path, int]] = []
    for path in root.rglob("*.jpg"):
        try:
            stat = path.stat()
        except OSError:
            continue
        used = known.get(str(path.resolve()).lower()) or ""
        files.append((used or f"{stat.st_atime:.6f}", path, int(stat.st_size)))
    files.sort()
    total = sum(size for _used, _path, size in files)
    removed = 0
    referenced = set(known)
    for used, path, size in files:
        key = str(path.resolve()).lower()
        orphan = key not in referenced
        if total <= max_bytes and not orphan:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        removed += 1
        if orphan:
            continue
        store.conn.execute("DELETE FROM library_thumbs WHERE thumb_path = ?", (str(path),))
    store.conn.commit()
    return removed


def ensure_library_thumbnail(store: LibraryStore, item: LibraryItem) -> LibraryItem:
    """Copy a thumb that already exists. Does not run ffmpeg."""
    current = Path(item.thumb_path) if item.thumb_path else None
    if current is not None and current.is_file() and current.stat().st_size > 32:
        return item
    if item.job_id:
        try:
            job = store.repo.get(item.job_id)
        except Exception:  # noqa: BLE001
            job = None
        raw = getattr(job, "thumbnail_path", None) if job is not None else None
        if raw and Path(str(raw)).is_file():
            try:
                return store.set_thumb_path(item.id, raw)
            except Exception:  # noqa: BLE001
                log.exception("Failed to store job thumbnail on library item %s", item.id)
    return item


def record_file_probe(store: Any, file_id: int, probed: Any) -> None:
    from frameforge.db.repository import utc_now

    if probed is None:
        store.set_file_probe(file_id, probed_at=utc_now())
        return
    duration_ms = int(probed.duration * 1000) if probed.duration is not None else None
    store.set_file_probe(
        file_id,
        width=probed.width,
        height=probed.height,
        rotation=probed.rotation,
        duration_ms=duration_ms,
        fps=probed.fps,
        vcodec=probed.vcodec,
        acodec=probed.acodec,
        pix_fmt=probed.pix_fmt,
        size_bytes=probed.size,
        probed_at=utc_now(),
    )
