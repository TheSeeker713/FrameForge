"""FrameForge directory contract: never dump into a bare picked folder.

Policy: keep per-site folders (youtube/, x.com/, …) as media homes.
Repair moves only loose thumbs, SQLite files, root-level videos, and records junk
candidates — it never deletes.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from frameforge.library.paths import VIDEO_SUFFIXES, unique_dest
from frameforge.library.taxonomy import INGEST_FOLDER, PRIVATE_FOLDER

log = logging.getLogger(__name__)

APP_DIR_NAME = "FrameForge"
LIBRARY_DIR_NAME = "Library"
THUMB_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
DB_BASENAME = "frameforge.db"
DB_SIDECARS = (DB_BASENAME, f"{DB_BASENAME}-wal", f"{DB_BASENAME}-shm")
# Directories that are not per-site media homes (do not harvest thumbs from these).
CONTRACT_DIRS = frozenset(
    {
        "thumbnails",
        "database",
        "cookies",
        "archive",
        "temp",
        "models",
        "upscaled",
        "converted",
        PRIVATE_FOLDER.lower(),
    }
)


def resolve_library_home(picked: str | Path) -> Path:
    """Map a folder pick to ``<picked>/FrameForge/Library``.

    If the user already picked FrameForge or FrameForge/Library, do not nest another FrameForge.
    """
    picked = Path(picked).expanduser().resolve()
    if picked.name.lower() == LIBRARY_DIR_NAME.lower() and picked.parent.name.lower() == APP_DIR_NAME.lower():
        return picked
    if picked.name.lower() == APP_DIR_NAME.lower():
        return picked / LIBRARY_DIR_NAME
    return picked / APP_DIR_NAME / LIBRARY_DIR_NAME


def ensure_library_tree(home: str | Path) -> Path:
    """Create Library/Uncategorized plus sibling thumbnails/ and database/ under FrameForge."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / INGEST_FOLDER).mkdir(parents=True, exist_ok=True)
    forge = home.parent if home.name.lower() == LIBRARY_DIR_NAME.lower() else home / APP_DIR_NAME
    if forge.name.lower() != APP_DIR_NAME.lower():
        forge = home / APP_DIR_NAME
        forge.mkdir(parents=True, exist_ok=True)
    (forge / "thumbnails").mkdir(parents=True, exist_ok=True)
    (forge / "database").mkdir(parents=True, exist_ok=True)
    return home.resolve()


def _move_unique(src: Path, dest_dir: Path) -> Path | None:
    if not src.is_file():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_dest(dest_dir, src.name)
    shutil.move(str(src), str(dest))
    return dest


def _move_db_sidecar(src: Path, dest_dir: Path) -> Path | None:
    """Move SQLite files. Never overwrite an existing database/frameforge.db."""
    if not src.is_file():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        if src.resolve() == dest.resolve():
            return dest
        dest = unique_dest(dest_dir, src.name)
        if dest.exists() and src.resolve() == dest.resolve():
            return dest
    shutil.move(str(src), str(dest))
    return dest


def _remap_thumb_path(conn: object, old: Path, new: Path) -> int:
    old_s = str(old)
    new_s = str(new)
    n = 0
    try:
        cur = conn.execute(  # type: ignore[union-attr]
            "UPDATE library_items SET thumb_path = ? WHERE thumb_path = ?",
            (new_s, old_s),
        )
        n += int(cur.rowcount or 0)
    except Exception:  # noqa: BLE001
        log.exception("Failed to remap library_items.thumb_path %s -> %s", old_s, new_s)
    try:
        rows = conn.execute("SELECT id, options_json FROM jobs").fetchall()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        rows = []
    for row in rows:
        raw = row["options_json"] if not isinstance(row, tuple) else row[1]
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        tp = data.get("thumbnail_path")
        if not tp or str(tp) != old_s:
            continue
        data["thumbnail_path"] = new_s
        jid = row["id"] if not isinstance(row, tuple) else row[0]
        conn.execute(  # type: ignore[union-attr]
            "UPDATE jobs SET options_json = ? WHERE id = ?",
            (json.dumps(data), jid),
        )
        n += 1
    try:
        conn.commit()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    return n


def _count_junk(folders: list[Path]) -> int:
    from frameforge.library.junk import find_junk

    return len(find_junk(folders))


def _media_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name.lower() in CONTRACT_DIRS:
            continue
        found.append(child)
    return found


def repair_frameforge_tree(
    root: str | Path,
    *,
    site_folders: bool = True,
    conn: object | None = None,
) -> dict[str, int]:
    """Organize thumbs/db/root videos. Keep per-site folders as media homes. Never deletes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    thumbs = root / "thumbnails"
    database = root / "database"
    videos = root / "videos"
    thumbs.mkdir(parents=True, exist_ok=True)
    database.mkdir(parents=True, exist_ok=True)
    videos.mkdir(parents=True, exist_ok=True)
    moved = {"thumbs": 0, "db": 0, "videos": 0, "junk_candidates": 0, "thumb_paths_updated": 0}
    if not root.is_dir():
        return moved
    for child in list(root.iterdir()):
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        name = child.name
        is_db = (
            name in DB_SIDECARS
            or name.startswith(f"{DB_BASENAME}-")
            or name.startswith(f"{DB_BASENAME}.")
            or suffix == ".db"
        )
        if is_db:
            dest = _move_db_sidecar(child, database)
            if dest is not None and dest.resolve() != child.resolve():
                moved["db"] += 1
            continue
        if suffix in THUMB_SUFFIXES:
            dest = _move_unique(child, thumbs)
            if dest is not None:
                moved["thumbs"] += 1
                if conn is not None:
                    moved["thumb_paths_updated"] += _remap_thumb_path(conn, child, dest)
            continue
        if suffix in VIDEO_SUFFIXES:
            dest = _move_unique(child, videos)
            if dest is not None:
                moved["videos"] += 1
    if site_folders:
        media = _media_dirs(root)
        for folder in media:
            for path in list(folder.rglob("*")):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if suffix in THUMB_SUFFIXES:
                    dest = _move_unique(path, thumbs)
                    if dest is not None:
                        moved["thumbs"] += 1
                        if conn is not None:
                            moved["thumb_paths_updated"] += _remap_thumb_path(conn, path, dest)
        moved["junk_candidates"] = _count_junk(media)
    log.info(
        "Folder repair at %s: thumbs=%s db=%s videos=%s junk_candidates=%s thumb_paths_updated=%s",
        root,
        moved["thumbs"],
        moved["db"],
        moved["videos"],
        moved["junk_candidates"],
        moved["thumb_paths_updated"],
    )
    return moved
