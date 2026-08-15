"""Local thumbnail cache under the FrameForge data root."""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from frameforge.paths import ensure_output_tree, thumbnails_dir

_TIMEOUT = 20.0
_MAX_BYTES = 8 * 1024 * 1024
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_COMPLETED = frozenset({"completed", "download_completed"})


def thumbnail_path_for_job(job_id: int, suffix: str = ".jpg") -> Path:
    ensure_output_tree()
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    if ext.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"
    return thumbnails_dir() / f"{int(job_id)}{ext}"


def thumbnail_url_from_info(info: dict[str, Any] | None) -> str | None:
    if not info:
        return None
    url = info.get("thumbnail")
    if isinstance(url, str) and url.startswith(("http://", "https://", "file:")):
        return url
    thumbs = info.get("thumbnails") or []
    if isinstance(thumbs, list) and thumbs:
        best = thumbs[-1]
        if isinstance(best, dict):
            u = best.get("url")
            if isinstance(u, str) and u:
                return u
        elif isinstance(best, str):
            return best
    return None


def _suffix_from_url_or_type(url: str, content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if ct in mapping:
        return mapping[ct]
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def download_thumbnail(url: str, dest: Path, *, timeout: float = _TIMEOUT) -> Path | None:
    """Fetch *url* to *dest*. Returns dest on success, None on any failure."""
    if not url:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "FrameForge/0.3"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = resp.read(_MAX_BYTES + 1)
            if not data or len(data) > _MAX_BYTES:
                return None
            ctype = resp.headers.get("Content-Type")
        suffix = _suffix_from_url_or_type(url, ctype)
        out = dest.with_suffix(suffix)
        out.write_bytes(data)
        return out
    except Exception:  # noqa: BLE001
        return None


def list_thumbnail_jobs(repo: Any, *, limit: int = 48) -> list[Any]:
    """Recent jobs that have a local thumbnail file, newest first."""
    found: list[Any] = []
    for job in repo.list_jobs():
        path = getattr(job, "thumbnail_path", None)
        if path and Path(path).is_file():
            found.append(job)
    found.sort(key=lambda j: j.updated_at or j.created_at or "", reverse=True)
    return found[: max(0, int(limit))]


def sidecar_thumbnail_near(media: Path | str | None) -> Path | None:
    """yt-dlp --write-thumbnail file next to the downloaded media."""
    if not media:
        return None
    path = Path(media)
    parent = path.parent
    stem = path.stem
    candidates: list[Path] = []
    for ext in _IMAGE_EXTS:
        candidates.append(parent / f"{stem}{ext}")
        candidates.append(parent / f"{path.name}{ext}")
    if parent.is_dir():
        for child in parent.iterdir():
            if not child.is_file():
                continue
            if child.suffix.lower() not in _IMAGE_EXTS:
                continue
            if child.stem == stem or child.name.startswith(stem + "."):
                candidates.append(child)
    seen: set[Path] = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if cand.is_file() and cand.stat().st_size > 32:
            return cand
    return None


def _copy_into_cache(job_id: int, src: Path) -> Path | None:
    if not src.is_file() or src.stat().st_size < 32:
        return None
    dest = thumbnail_path_for_job(job_id, src.suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dest.resolve() != src.resolve():
            dest.write_bytes(src.read_bytes()[:_MAX_BYTES])
        return dest if dest.is_file() else None
    except OSError:
        return None


def extract_video_still(media: Path | str | None, dest: Path) -> Path | None:
    """Best-effort first-frame JPEG via ffmpeg. Never raises."""
    if not media:
        return None
    src = Path(media)
    if not src.is_file() or src.stat().st_size < 256:
        return None
    from frameforge.download.invocation import ffmpeg_location

    ffmpeg = ffmpeg_location()
    if not ffmpeg:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = dest.with_suffix(".jpg")
    try:
        proc = subprocess.run(  # noqa: S603
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "1",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-q:v",
                "4",
                str(out),
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode == 0 and out.is_file() and out.stat().st_size > 32:
            return out
    except Exception:  # noqa: BLE001
        return None
    return None


def _info_from_sidecar(media: Path | str | None) -> dict[str, Any]:
    if not media:
        return {}
    path = Path(media)
    for cand in (path.with_suffix(path.suffix + ".info.json"), path.with_name(path.stem + ".info.json")):
        if cand.is_file():
            try:
                import json

                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:  # noqa: BLE001
                return {}
    return {}


def cache_job_thumbnail(
    repo: Any,
    job_id: int,
    *,
    thumbnail_url: str | None = None,
    info: dict[str, Any] | None = None,
    media_path: str | Path | None = None,
    extract_still: bool = True,
) -> Path | None:
    """Store a thumbnail for *job_id*. Never raises; missing thumbs are skipped."""
    try:
        job = repo.get(int(job_id))
        existing = getattr(job, "thumbnail_path", None)
        if existing and Path(existing).is_file():
            return Path(existing)
        media = media_path or getattr(job, "download_path", None) or getattr(job, "output_path", None)
        sidecar = sidecar_thumbnail_near(media)
        if sidecar is not None:
            path = _copy_into_cache(job_id, sidecar)
            if path is not None:
                repo.merge_options(int(job_id), {"thumbnail_path": str(path)})
                return path
        blob = info if info else _info_from_sidecar(media)
        url = thumbnail_url or thumbnail_url_from_info(blob)
        if url:
            dest = thumbnail_path_for_job(job_id)
            path = download_thumbnail(url, dest)
            if path is not None and path.is_file():
                repo.merge_options(int(job_id), {"thumbnail_path": str(path)})
                return path
        if extract_still and media:
            dest = thumbnail_path_for_job(job_id, ".jpg")
            still = extract_video_still(media, dest)
            if still is not None:
                repo.merge_options(int(job_id), {"thumbnail_path": str(still)})
                return still
        return None
    except Exception:  # noqa: BLE001
        return None


def backfill_missing_thumbnails(
    repo: Any,
    *,
    limit: int = 48,
    extract_still: bool = False,
) -> int:
    """Fill thumbnail_path for completed jobs that still have none. Returns count stored."""
    stored = 0
    for job in repo.list_jobs():
        if stored >= max(0, int(limit)):
            break
        if getattr(job, "status", None) not in _COMPLETED:
            continue
        path = getattr(job, "thumbnail_path", None)
        if path and Path(path).is_file():
            continue
        media = getattr(job, "download_path", None) or getattr(job, "output_path", None)
        if cache_job_thumbnail(repo, job.id, media_path=media, extract_still=extract_still):
            stored += 1
    return stored
