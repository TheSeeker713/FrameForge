"""FrameForge directory contract: never dump into a bare picked folder."""

from __future__ import annotations

import shutil
from pathlib import Path

from frameforge.library.paths import VIDEO_SUFFIXES
from frameforge.library.taxonomy import INGEST_FOLDER

APP_DIR_NAME = "FrameForge"
LIBRARY_DIR_NAME = "Library"
THUMB_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
DB_BASENAME = "frameforge.db"
DB_SIDECARS = (DB_BASENAME, f"{DB_BASENAME}-wal", f"{DB_BASENAME}-shm")


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


def _safe_move(src: Path, dest_dir: Path) -> Path | None:
    if not src.is_file():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        return dest
    shutil.move(str(src), str(dest))
    return dest


def repair_frameforge_tree(root: str | Path) -> dict[str, int]:
    """Move loose thumbs/db/videos at the FrameForge root into subfolders. Never deletes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    thumbs = root / "thumbnails"
    database = root / "database"
    videos = root / "videos"
    thumbs.mkdir(parents=True, exist_ok=True)
    database.mkdir(parents=True, exist_ok=True)
    videos.mkdir(parents=True, exist_ok=True)
    moved = {"thumbs": 0, "db": 0, "videos": 0}
    if not root.is_dir():
        return moved
    for child in list(root.iterdir()):
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        if child.name in DB_SIDECARS or child.name.startswith(f"{DB_BASENAME}-"):
            if _safe_move(child, database):
                moved["db"] += 1
            continue
        if suffix in THUMB_SUFFIXES:
            if _safe_move(child, thumbs):
                moved["thumbs"] += 1
            continue
        if suffix in VIDEO_SUFFIXES:
            if _safe_move(child, videos):
                moved["videos"] += 1
    return moved
