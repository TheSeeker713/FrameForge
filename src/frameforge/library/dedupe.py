"""Detect and merge duplicate library videos by normalized title + size + duration."""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from frameforge.library.models import LibraryItem
from frameforge.library.scan import list_playable_items
from frameforge.library.store import LibraryStore
from frameforge.util.recycle import send_to_recycle_bin

_BRACKETS = re.compile(r"\s*\[[^\[\]]*\]")
_SPACES = re.compile(r"\s+")


def normalize_title(title: str | None, *, path: str | None = None) -> str:
    raw = str(title or "").strip() or (Path(path).stem if path else "")
    raw = Path(raw).stem
    raw = _BRACKETS.sub(" ", raw)
    return _SPACES.sub(" ", raw).strip().lower()


def probe_duration(path: Path) -> float | None:
    from frameforge.download.invocation import ffprobe_location

    exe = ffprobe_location()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        data = json.loads(proc.stdout)
        value = data.get("format", {}).get("duration")
        return float(value) if value is not None else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def cached_duration(store: LibraryStore, item: LibraryItem) -> float | None:
    if item.duration is not None:
        return float(item.duration)
    path = Path(item.path)
    if not path.is_file():
        return None
    value = probe_duration(path)
    if value is not None:
        store.set_item_duration(item.id, value)
        return value
    return None


def _size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _identity(store: LibraryStore, item: LibraryItem) -> tuple[str, int, float] | None:
    path = Path(item.path)
    size = _size(path)
    if size is None:
        return None
    duration = cached_duration(store, item)
    if duration is None:
        return None
    title = normalize_title(item.title, path=item.path)
    if not title:
        return None
    return (title, size, round(duration, 2))


def pick_keeper(items: list[LibraryItem]) -> LibraryItem:
    def key(item: LibraryItem) -> tuple:
        path = Path(item.path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        height = item.height or 0
        width = item.width or 0
        return (height, width, mtime, -item.id)

    return max(items, key=key)


@dataclass
class DuplicateGroup:
    key: tuple[str, int, float]
    items: list[LibraryItem]
    keeper_id: int

    @property
    def extras(self) -> list[LibraryItem]:
        return [i for i in self.items if i.id != self.keeper_id]


@dataclass
class MergeReport:
    kept: int = 0
    recycled: int = 0
    groups: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return f"Kept {self.kept}, recycled {self.recycled} duplicate(s) in {self.groups} group(s)"


def find_duplicate_groups(store: LibraryStore) -> list[DuplicateGroup]:
    buckets: dict[tuple[str, int, float], list[LibraryItem]] = defaultdict(list)
    for item in list_playable_items(store):
        ident = _identity(store, item)
        if ident is None:
            continue
        buckets[ident].append(item)
    groups: list[DuplicateGroup] = []
    for key, items in buckets.items():
        if len(items) < 2:
            continue
        keeper = pick_keeper(items)
        groups.append(DuplicateGroup(key=key, items=items, keeper_id=keeper.id))
    return groups


def merge_duplicate_groups(
    store: LibraryStore,
    groups: list[DuplicateGroup] | None = None,
    *,
    recycle: bool = True,
) -> MergeReport:
    report = MergeReport()
    batch = groups if groups is not None else find_duplicate_groups(store)
    report.groups = len(batch)
    for group in batch:
        keeper = next((i for i in group.items if i.id == group.keeper_id), group.items[0])
        report.kept += 1
        for extra in group.extras:
            path = Path(extra.path)
            try:
                if path.is_file():
                    send_to_recycle_bin(path, recycle=recycle)
                store.remove_item(extra.id)
                report.recycled += 1
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"{path.name}: {exc}")
    return report
