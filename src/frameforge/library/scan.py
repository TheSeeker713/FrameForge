"""Heal library paths and find video files on disk that are not indexed."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from frameforge.library.ingest import index_folder
from frameforge.library.models import LibraryItem
from frameforge.library.paths import is_video_file, paths_equal
from frameforge.library.store import LibraryStore
from frameforge.library.taxonomy import INGEST_FOLDER, PRIVATE_FOLDER


def _skip_private(path: Path) -> bool:
    return PRIVATE_FOLDER.lower() in {part.lower() for part in path.parts}


def iter_videos(root: Path | None) -> list[Path]:
    if root is None or not Path(root).is_dir():
        return []
    found: list[Path] = []
    for path in Path(root).rglob("*"):
        if _skip_private(path):
            continue
        if is_video_file(path):
            found.append(path)
    return found


def videos_by_filename(root: Path | None) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in iter_videos(root):
        grouped[path.name.lower()].append(path)
    return grouped


def _prefer_hit(hits: list[Path]) -> Path:
    uncat = [p for p in hits if INGEST_FOLDER.lower() in {part.lower() for part in p.parts}]
    pool = uncat or hits
    return sorted(pool, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def resolve_item_path(item: LibraryItem, root: Path | None, by_name: dict[str, list[Path]] | None = None) -> Path | None:
    current = Path(item.path)
    if current.is_file():
        return current
    index = by_name if by_name is not None else videos_by_filename(root)
    hits = index.get(current.name.lower(), [])
    if not hits:
        return None
    return _prefer_hit(hits)


def heal_item(store: LibraryStore, item: LibraryItem, by_name: dict[str, list[Path]] | None = None) -> LibraryItem:
    found = resolve_item_path(item, store.root(), by_name)
    if found is None:
        return item
    if paths_equal(item.path, found):
        return item
    return store.update_item_path(item.id, found)


def heal_library_paths(store: LibraryStore) -> int:
    """Update library_items.path when the file moved under library_root. Returns healed count."""
    by_name = videos_by_filename(store.root())
    healed = 0
    for item in store.list_items(include_private=True):
        updated = heal_item(store, item, by_name)
        if updated.path != item.path:
            healed += 1
    return healed


def list_playable_items(store: LibraryStore, **kwargs) -> list[LibraryItem]:
    """Indexed items whose media file exists (after a re-find under library_root)."""
    by_name = videos_by_filename(store.root())
    playable: list[LibraryItem] = []
    for item in store.list_items(**kwargs):
        healed = heal_item(store, item, by_name)
        if Path(healed.path).is_file():
            playable.append(healed)
    return playable


def orphan_videos(store: LibraryStore) -> list[Path]:
    """Videos under library_root that are not in library_items."""
    orphans: list[Path] = []
    for path in iter_videos(store.root()):
        if store.get_by_path(path) is None:
            orphans.append(path)
    return orphans


def scan_library_folder(store: LibraryStore) -> list[LibraryItem]:
    """Index orphan videos already under library_root (no move). Toolbar Scan uses this."""
    heal_library_paths(store)
    root = store.root()
    if root is None:
        return []
    return index_folder(store, root)


def scan_ingest_folder(store: LibraryStore) -> list[LibraryItem]:
    """Index videos already in Uncategorized (post-migrate). Avoids walking a huge mis-set root."""
    heal_library_paths(store)
    try:
        dest = store.ingest_dir()
    except RuntimeError:
        return []
    return index_folder(store, dest)


DOWNLOAD_SCAN_SKIP = frozenset(
    {
        "models",
        "temp",
        "cookies",
        "archive",
        "thumbnails",
        "database",
        "upscaled",
        "converted",
        "metadata",
        PRIVATE_FOLDER.lower(),
    }
)


def download_videos_not_in_library(
    store: LibraryStore,
    *,
    roots: list[Path] | None = None,
) -> list[Path]:
    """Videos under the download tree that are not indexed and not already in library_root."""
    lib = store.root()
    lib_res = lib.resolve() if lib is not None and lib.exists() else None
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots or []:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not is_video_file(path):
                continue
            try:
                if path.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            name = path.name.lower()
            if name.endswith(".part") or ".part." in name or name.endswith(".aria2"):
                continue
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            parts = {part.lower() for part in rel.parts[:-1]}
            if parts & DOWNLOAD_SCAN_SKIP:
                continue
            resolved = path.resolve()
            if lib_res is not None:
                try:
                    resolved.relative_to(lib_res)
                    continue
                except ValueError:
                    pass
            if store.get_by_path(path) is not None or store.get_by_path(resolved) is not None:
                continue
            key = str(resolved).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(path)
    return found
