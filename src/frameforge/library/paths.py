"""Filesystem helpers for the local Library (no Explorer theme/DWM)."""

from __future__ import annotations

import re
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".wmv", ".mpeg", ".mpg"}
)


def safe_folder_name(name: str) -> str:
    text = _ILLEGAL.sub("", str(name or "").strip()).strip(" .")
    return (text or "Uncategorized")[:80]


def unique_dest(folder: Path, filename: str) -> Path:
    """Return folder/filename, adding ' (2)' … if the name is taken."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    raw = Path(filename).name
    dest = folder / raw
    if not dest.exists():
        return dest
    stem = Path(raw).stem
    suffix = Path(raw).suffix
    n = 2
    while True:
        cand = folder / f"{stem} ({n}){suffix}"
        if not cand.exists():
            return cand
        n += 1
        if n > 10_000:
            raise OSError(f"Could not find a free name under {folder}")


def paths_equal(a: str | Path, b: str | Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(Path(a)).lower() == str(Path(b)).lower()


def is_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
