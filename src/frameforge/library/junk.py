"""Junk file triage. Deletes go to the Recycle Bin only (never a permanent-delete API)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from frameforge.library.paths import VIDEO_SUFFIXES, is_video_file
from frameforge.util.recycle import send_to_recycle_bin

JUNK_SUFFIXES = frozenset({".part", ".ytdl", ".temp", ".tmp", ".download", ".aria2"})
SIDECAR_SUFFIXES = (".info.json", ".json", ".description", ".annotations.xml")


@dataclass
class JunkFile:
    path: Path
    reason: str


def _has_matching_video(path: Path) -> bool:
    stem = path.name
    for suffix in SIDECAR_SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        stem = path.stem
    parent = path.parent
    return any((parent / f"{stem}{ext}").is_file() for ext in VIDEO_SUFFIXES)


def classify_junk(path: Path) -> str | None:
    if not path.is_file():
        return None
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in JUNK_SUFFIXES or name.endswith(".part") or ".part." in name or name.endswith(".aria2"):
        return "incomplete download"
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0 and (suffix in VIDEO_SUFFIXES or suffix in JUNK_SUFFIXES or name.endswith(".json")):
        return "zero-byte"
    for extra in SIDECAR_SUFFIXES:
        if name.endswith(extra) and not _has_matching_video(path):
            return "orphan sidecar"
    return None


def find_junk(roots: list[Path]) -> list[JunkFile]:
    found: list[JunkFile] = []
    seen: set[str] = set()
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if is_video_file(path) and path.stat().st_size > 0:
                continue
            reason = classify_junk(path)
            if not reason:
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(JunkFile(path=path, reason=reason))
    return found


def recycle_junk(paths: list[Path], *, recycle: bool = True) -> list[Path]:
    removed: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        send_to_recycle_bin(path, recycle=recycle)
        removed.append(path)
    return removed


def move_junk(paths: list[Path], dest_dir: Path) -> list[Path]:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for path in paths:
        if not path.is_file():
            continue
        target = dest_dir / path.name
        shutil.move(str(path), str(target))
        moved.append(target)
    return moved
