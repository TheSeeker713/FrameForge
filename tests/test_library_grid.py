"""Library grid binds playable items; play uses the default player."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.actions import play_library_item
from frameforge.library.scan import heal_library_paths, list_playable_items, orphan_videos, scan_library_folder
from frameforge.library.store import LibraryStore
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.components.library import library_tile
from tests.test_library import _clip, _completed_job, _repo


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    return ui


def test_grid_binds_one_card_per_playable_item(tmp_path: Path):
    from frameforge.library.ingest import ingest_completed_jobs

    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    for i, name in enumerate(("one", "two", "three")):
        src = _clip(tmp_path / "dl" / f"{name}.mp4")
        _completed_job(ui.repo, src, title=name, url=f"https://www.youtube.com/watch?v={name}{i}")
    ingest_completed_jobs(ui.repo, ui.library)
    ui.refresh_library()
    items = list_playable_items(ui.library)
    assert len(items) == 3
    assert ui.library_visible_count == 3
    assert len(ui.library_grid.controls) == 3
    assert ui.library_grid.visible is True
    assert ui.library_empty.visible is False
    assert ui.library_toolbar.data["count"] == 3
    titles = {str(c.data.get("path")) for c in ui.library_grid.controls}
    assert len(titles) == 3
    ui.shutdown()


def test_missing_thumb_still_renders_tile(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "clip.mp4")
    job = _completed_job(repo, src, title="Clip")
    item = store.add_item(
        path=src,
        title="Clip",
        job_id=job.id,
        thumb_path=str(tmp_path / "missing.webp"),
    )
    tile = library_tile(item, on_play=lambda _i: None)
    assert tile.data["item_id"] == item.id
    assert tile.on_click is not None
    repo.close()


def test_heal_missing_path_under_library_root(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    root = store.complete_onboarding(tmp_path / "Lib")
    dest = _clip(root / "Uncategorized" / "moved.mp4")
    item = store.add_item(path=tmp_path / "gone" / "moved.mp4", title="Moved")
    assert not Path(item.path).is_file()
    healed = heal_library_paths(store)
    assert healed == 1
    playable = list_playable_items(store)
    assert len(playable) == 1
    assert Path(playable[0].path).resolve() == dest.resolve()
    repo.close()


def test_scan_indexes_disk_orphans(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    root = store.complete_onboarding(tmp_path / "Lib")
    indexed = _clip(root / "Uncategorized" / "known.mp4")
    store.add_item(path=indexed, title="known")
    orphan = _clip(root / "Uncategorized" / "orphan.mp4")
    assert len(orphan_videos(store)) == 1
    added = scan_library_folder(store)
    assert len(added) == 1
    assert Path(added[0].path).resolve() == orphan.resolve()
    assert orphan_videos(store) == []
    assert len(list_playable_items(store)) == 2
    repo.close()


def test_play_opens_default_player_path(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    root = store.complete_onboarding(tmp_path / "Lib")
    src = _clip(root / "Uncategorized" / "play.mp4")
    item = store.add_item(path=src, title="Play me")
    opened = play_library_item(item, launch=False)
    assert opened.resolve() == src.resolve()
    ui = FrameForgeUi(repo=repo, worker=SequentialWorker(repo, download_handler=lambda j, r: None), start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    ui.refresh_library()
    assert ui.library_visible_count == 1
    ui.play_library_item(item.id)
    ui.shutdown()


def test_ui_scan_fills_blank_library(tmp_path: Path):
    ui = _ui(tmp_path)
    root = ui.library.complete_onboarding(tmp_path / "Lib")
    _clip(root / "Uncategorized" / "disk-only.mp4")
    ui.refresh_library()
    assert ui.library_visible_count == 0
    assert ui.library_toolbar.data["orphan_count"] == 1
    assert "Scan" in str(ui.library_empty.data.get("cta"))
    n = ui.scan_library_folder()
    assert n == 1
    assert ui.library_visible_count == 1
    assert len(ui.library_grid.controls) == 1
    ui.shutdown()
