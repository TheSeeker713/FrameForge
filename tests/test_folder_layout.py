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


def test_repair_sweeps_site_folder_thumbs_keeps_videos(tmp_path: Path):
    root = tmp_path / "FrameForge"
    yt = root / "youtube"
    yt.mkdir(parents=True)
    (yt / "clip.mp4").write_bytes(b"media")
    (yt / "clip.webp").write_bytes(b"thumb")
    (yt / "clip.part").write_bytes(b"partial")
    (root / "thumbnails").mkdir()
    (root / "thumbnails" / "clip.webp").write_bytes(b"existing")
    moved = repair_frameforge_tree(root, site_folders=True)
    assert moved["thumbs"] == 1
    assert (yt / "clip.mp4").is_file()
    assert not (yt / "clip.webp").exists()
    assert (root / "thumbnails" / "clip.webp").read_bytes() == b"existing"
    assert (root / "thumbnails" / "clip (2).webp").is_file()
    assert (yt / "clip.part").is_file()
    assert moved["junk_candidates"] >= 1


def test_repair_site_folders_false_leaves_youtube_thumbs(tmp_path: Path):
    root = tmp_path / "FrameForge"
    yt = root / "youtube"
    yt.mkdir(parents=True)
    (yt / "clip.webp").write_bytes(b"thumb")
    (yt / "clip.mp4").write_bytes(b"media")
    repair_frameforge_tree(root, site_folders=False)
    assert (yt / "clip.webp").is_file()
    assert (yt / "clip.mp4").is_file()


def test_repair_updates_job_and_library_thumb_paths(tmp_path: Path):
    from tests.test_library import _clip, _completed_job

    root = tmp_path / "FrameForge"
    yt = root / "youtube"
    yt.mkdir(parents=True)
    thumb = yt / "show.webp"
    thumb.write_bytes(b"thumb")
    (yt / "show.mp4").write_bytes(b"media")
    repo = _repo(tmp_path)
    job = _completed_job(repo, _clip(tmp_path / "dl" / "show.mp4"), title="show")
    repo.merge_options(job.id, {"thumbnail_path": str(thumb)})
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    store.add_item(path=tmp_path / "dl" / "show.mp4", title="show", thumb_path=str(thumb))
    moved = repair_frameforge_tree(root, site_folders=True, conn=repo.conn)
    assert moved["thumbs"] == 1
    assert moved["thumb_paths_updated"] >= 1
    dest = root / "thumbnails" / "show.webp"
    assert dest.is_file()
    assert repo.get(job.id).thumbnail_path == str(dest)
    item = store.list_items()[0]
    assert item.thumb_path == str(dest)
    repo.close()


def test_settings_has_repair_folders_action():
    from frameforge.ui_flet.components.settings_dialog import build_settings_dialog
    from tests.test_library import _repo

    # signature only — dialog build needs a repo; covered in dead-clicks with extra kw
    import inspect

    sig = inspect.signature(build_settings_dialog)
    assert "on_repair_folders" in sig.parameters
