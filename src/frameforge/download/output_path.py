"""Resolve the on-disk media path after yt-dlp exits 0."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}
SKIP_SUFFIXES = {".part", ".ytdl", ".temp", ".aria2", ".json", ".jpg", ".jpeg", ".png", ".webp", ".vtt", ".srt"}
SKIP_NAME_ENDINGS = (
    ".part",
    ".ytdl",
    ".temp",
    ".aria2",
    ".info.json",
    ".description",
)
_ARCHIVE_SKIP_RE = re.compile(
    r"has already been recorded in (the )?archive|already in archive",
    re.IGNORECASE,
)
_FRAGMENT_RE = re.compile(r"\.f\d{2,4}\.[A-Za-z0-9]+$", re.IGNORECASE)
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class OutputMissingError(FileNotFoundError):
    """yt-dlp exited 0 (or claimed success) but no media file is on disk."""

    def __init__(
        self,
        url: str,
        *,
        archive_hit: bool = False,
        output_dir: Path | None = None,
    ) -> None:
        self.url = url
        self.archive_hit = bool(archive_hit)
        self.output_dir = output_dir
        if archive_hit:
            msg = "Archive lists this video but the file is missing on disk."
        else:
            msg = f"Downloaded file not found for {url}"
        super().__init__(msg)


@dataclass
class ResolvedOutput:
    path: Path | None
    recovery_method: str
    archive_hit: bool
    video_id: str | None = None


def video_id_from_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        ident = parsed.path.strip("/").split("/")[0]
        return ident if _YT_ID_RE.match(ident) else None
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"] and _YT_ID_RE.match(qs["v"][0]):
        return qs["v"][0]
    parts = [p for p in parsed.path.split("/") if p]
    if "shorts" in parts or "embed" in parts or "live" in parts:
        ident = parts[-1]
        return ident if _YT_ID_RE.match(ident) else None
    return None


def is_sidecar(path: Path) -> bool:
    name = path.name.lower()
    if any(name.endswith(end) for end in SKIP_NAME_ENDINGS):
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return False


def is_media_file(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
    except OSError:
        return False
    if is_sidecar(path):
        return False
    return path.suffix.lower() in MEDIA_SUFFIXES


def normalize_printed_path(raw: str, output_dir: Path) -> Path | None:
    text = str(raw or "").strip().strip('"').strip("'")
    if not text or text.upper() in {"NA", "N/A", "NONE", "NULL"}:
        return None
    p = Path(text)
    candidates = [p] if p.is_absolute() else [output_dir / p, Path(text)]
    for cand in candidates:
        try:
            resolved = cand.resolve() if cand.exists() else cand
        except OSError:
            resolved = cand
        if is_media_file(resolved):
            return resolved
    return None


def looks_like_filepath_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text or text.upper() in {"NA", "N/A"}:
        return False
    lower = text.lower()
    if any(lower.endswith(ext) for ext in MEDIA_SUFFIXES):
        return True
    if ":\\" in text or text.startswith("\\\\") or text.startswith("/"):
        return True
    return False


def archive_skip_in_text(text: str | None) -> bool:
    return bool(_ARCHIVE_SKIP_RE.search(str(text or "")))


def ytdlp_archive_contains(archive_file: Path | None, video_id: str | None) -> bool:
    if not archive_file or not video_id:
        return False
    path = Path(archive_file)
    if not path.is_file():
        return False
    needle = video_id.lower()
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if needle in line.lower().split():
                return True
    except OSError:
        return False
    return False


def _prefer_merged(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    merged = [p for p in paths if not _FRAGMENT_RE.search(p.name)]
    pool = merged or paths
    return sorted(pool, key=lambda p: p.stat().st_mtime)[-1]


def glob_by_video_id(output_dir: Path, video_id: str | None) -> Path | None:
    if not video_id or not output_dir.is_dir():
        return None
    found: list[Path] = []
    try:
        for path in output_dir.glob(f"*{video_id}*"):
            if is_media_file(path):
                found.append(path)
    except OSError:
        return None
    return _prefer_merged(found)


def glob_recent_media(
    output_dir: Path,
    *,
    video_id: str | None = None,
    window_sec: float = 600,
) -> Path | None:
    if not output_dir.is_dir():
        return None
    now = time.time()
    found: list[Path] = []
    try:
        for path in output_dir.iterdir():
            if not is_media_file(path):
                continue
            if video_id and video_id not in path.name:
                continue
            try:
                if (now - path.stat().st_mtime) > window_sec:
                    continue
            except OSError:
                continue
            found.append(path)
    except OSError:
        return None
    return _prefer_merged(found)


def filename_from_infojson(output_dir: Path, video_id: str | None) -> Path | None:
    if not output_dir.is_dir():
        return None
    files: list[Path] = []
    try:
        if video_id:
            files.extend(output_dir.glob(f"*{video_id}*.info.json"))
        if not files:
            files.extend(output_dir.glob("*.info.json"))
    except OSError:
        return None
    files = sorted(files, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for info in files[:8]:
        try:
            data: dict[str, Any] = json.loads(info.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for key in ("_filename", "filename", "filepath"):
            raw = data.get(key)
            if not raw:
                continue
            found = normalize_printed_path(str(raw), output_dir)
            if found:
                return found
        ident = str(data.get("id") or "")
        if ident:
            by_id = glob_by_video_id(output_dir, ident)
            if by_id:
                return by_id
    return None


def resolve_download_artifact(
    *,
    url: str,
    output_dir: Path,
    printed: list[str] | tuple[str, ...] = (),
    output_tail: list[str] | tuple[str, ...] = (),
    archive_file: Path | None = None,
) -> ResolvedOutput:
    """Find the media file after a successful yt-dlp run. Never guesses a missing path."""
    dest = Path(output_dir)
    video_id = video_id_from_url(url)
    blob = "\n".join([*printed, *output_tail])
    archive_hit = archive_skip_in_text(blob) or ytdlp_archive_contains(archive_file, video_id)

    for item in printed:
        found = normalize_printed_path(item, dest)
        if found:
            return ResolvedOutput(found, "printed_path", archive_hit, video_id)
        if _YT_ID_RE.match(item.strip()) and not video_id:
            video_id = item.strip()

    by_id = glob_by_video_id(dest, video_id)
    if by_id:
        return ResolvedOutput(by_id, "glob_id", archive_hit, video_id)

    recent = glob_recent_media(dest, video_id=video_id)
    if recent:
        return ResolvedOutput(recent, "glob_recent", archive_hit, video_id)

    from_json = filename_from_infojson(dest, video_id)
    if from_json:
        return ResolvedOutput(from_json, "infojson", archive_hit, video_id)

    return ResolvedOutput(None, "missing", archive_hit, video_id)


def require_download_artifact(**kwargs: Any) -> ResolvedOutput:
    resolved = resolve_download_artifact(**kwargs)
    if resolved.path is not None and is_media_file(resolved.path):
        return resolved
    raise OutputMissingError(
        str(kwargs.get("url") or ""),
        archive_hit=resolved.archive_hit,
        output_dir=kwargs.get("output_dir"),
    )
