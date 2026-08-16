"""FrameForge folder layout: library pick + download-root repair."""

from __future__ import annotations

from pathlib import Path

from frameforge.layout import repair_frameforge_tree, resolve_library_home
from frameforge.library.store import LibraryStore
from frameforge.paths import database_dir, db_path
from tests.test_library import _repo


def test_library_pick_creates_frameforge_library(tmp_path: Path):
    picked = tmp_path / "Videos"
    home = resolve_library_home(picked)
    assert home == picked / "FrameForge" / "Library"
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    stored = store.set_root(picked)
    assert stored == home.resolve()
    assert (home / "Uncategorized").is_dir()
    assert (picked / "FrameForge" / "thumbnails").is_dir()
    assert (picked / "FrameForge" / "database").is_dir()
    assert stored != picked.resolve()
    repo.close()


def test_library_pick_does_not_nest_frameforge(tmp_path: Path):
    forge = tmp_path / "FrameForge"
    assert resolve_library_home(forge) == forge / "Library"
    already = forge / "Library"
    assert resolve_library_home(already) == already.resolve()


def test_repair_moves_loose_thumbs_and_db(tmp_path: Path):
    root = tmp_path / "FrameForge"
    root.mkdir()
    (root / "shot.jpg").write_bytes(b"jpg")
    (root / "frameforge.db").write_bytes(b"sqlite")
    (root / "frameforge.db-wal").write_bytes(b"wal")
    (root / "clip.mp4").write_bytes(b"media")
    moved = repair_frameforge_tree(root)
    assert moved["thumbs"] == 1
    assert moved["db"] >= 1
    assert moved["videos"] == 1
    assert (root / "thumbnails" / "shot.jpg").is_file()
    assert not (root / "shot.jpg").exists()
    assert (root / "database" / "frameforge.db").is_file()
    assert not (root / "frameforge.db").exists()
    assert (root / "videos" / "clip.mp4").is_file()
    assert not (root / "clip.mp4").exists()


def test_db_path_is_under_database_dir():
    assert db_path() == database_dir() / "frameforge.db"
    assert db_path().parent.name == "database"
