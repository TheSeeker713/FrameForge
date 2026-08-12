"""Local thumbnail cache under the FrameForge data root."""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from frameforge.paths import ensure_output_tree, thumbnails_dir

_TIMEOUT = 20.0
_MAX_BYTES = 8 * 1024 * 1024


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


def cache_job_thumbnail(
    repo: Any,
    job_id: int,
    *,
    thumbnail_url: str | None = None,
    info: dict[str, Any] | None = None,
) -> Path | None:
    """Download a thumbnail for *job_id*. Never raises; missing thumbs are skipped."""
    try:
        url = thumbnail_url or thumbnail_url_from_info(info)
        if not url:
            return None
        dest = thumbnail_path_for_job(job_id)
        path = download_thumbnail(url, dest)
        if path is None or not path.is_file():
            return None
        repo.merge_options(int(job_id), {"thumbnail_path": str(path)})
        return path
    except Exception:  # noqa: BLE001
        return None
