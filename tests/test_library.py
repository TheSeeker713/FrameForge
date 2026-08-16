"""v0.6 Library — local filesystem + SQLite. No cloud."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.connection import connect
from frameforge.db.migrate import current_version, migrate
from frameforge.db.repository import JobRepository
from frameforge.library.actions import can_upscale_library_item, play_library_item, reveal_library_item
from frameforge.library.ingest import (
    assign_to_collection,
    completed_jobs_not_in_library,
    index_folder,
    ingest_completed_jobs,
)
from frameforge.library.store import LibraryStore
from frameforge.library.taxonomy import KIND_TYPE, SOURCES, SUBJECTS, TYPES
from frameforge.ui_flet.app import FrameForgeUi, build_tabs
from frameforge.ui_flet.theme import TAB_LABELS
from frameforge.queue.worker import SequentialWorker


def _repo(tmp_path: Path) -> JobRepository:
    return JobRepository(tmp_path / "library.db")


def _clip(path: Path, data: bytes = b"media") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _completed_job(repo: JobRepository, path: Path, *, title: str, height: int | None = 720, url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
    job = repo.enqueue(url, title=title, extractor="youtube")
    repo.update_status(job.id, "completed")
    repo.set_paths(job.id, download_path=str(path), output_path=str(path))
    if height is not None:
        repo.set_source_resolution(job.id, 1280, height)
    return repo.get(job.id)


def test_migration_creates_library_tables(tmp_path: Path):
    conn = connect(tmp_path / "m.db")
    assert migrate(conn) >= 4
    assert current_version(conn) >= 4
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "library_items" in names
    assert "library_collections" in names
    assert "library_item_collections" in names
    assert "library_watch_folders" in names
    conn.close()


def test_onboarding_sets_root(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    root = tmp_path / "MyLib"
    store.set_root(root)
    assert store.is_onboarded() is False
    assert store.onboarding_step() == "move"
    assert store.root() == root.resolve()
    assert (root / "Uncategorized").is_dir()
    store.mark_onboarded()
    assert store.is_onboarded()
    assert store.onboarding_step() == "done"
    repo.close()


def test_move_updates_paths_and_second_open_only_new(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    root = tmp_path / "Lib"
    store.complete_onboarding(root)
    src = _clip(tmp_path / "downloads" / "clip-a.mp4")
    job = _completed_job(repo, src, title="Clip A")
    first = ingest_completed_jobs(repo, store)
    assert len(first) == 1
    dest = Path(repo.get(job.id).download_path)
    assert dest.parent.name == "Uncategorized"
    assert dest.is_file()
    assert not src.exists()
    item = store.get_by_job_id(job.id)
    assert item is not None
    assert Path(item.path) == dest
    assert item.source == "YouTube"

    assert completed_jobs_not_in_library(repo, store) == []

    src2 = _clip(tmp_path / "downloads" / "clip-b.mp4")
    job2 = _completed_job(repo, src2, title="Clip B", url="https://www.youtube.com/watch?v=bbbb")
    pending = completed_jobs_not_in_library(repo, store)
    assert [p.id for p in pending] == [job2.id]
    ingest_completed_jobs(repo, store, pending)
    assert completed_jobs_not_in_library(repo, store) == []
    repo.close()


def test_ingest_reports_progress(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.set_root(tmp_path / "Lib")
    ticks: list[tuple[int, int]] = []
    _completed_job(repo, _clip(tmp_path / "dl" / "p1.mp4"), title="p1")
    _completed_job(repo, _clip(tmp_path / "dl" / "p2.mp4"), title="p2", url="https://www.youtube.com/watch?v=pppp")
    ingest_completed_jobs(repo, store, on_progress=lambda d, t, _j: ticks.append((d, t)))
    assert ticks == [(1, 2), (2, 2)]
    repo.close()


def test_play_reveal_and_4k_upscale_blocked(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "ok.mp4")
    job = _completed_job(repo, src, title="ok", height=1080)
    item = ingest_completed_jobs(repo, store)[0].item
    played = play_library_item(item, launch=False)
    revealed = reveal_library_item(item, launch=False)
    assert played.is_file()
    assert revealed.is_dir()
    assert can_upscale_library_item(item)

    src4k = _clip(tmp_path / "dl" / "uhd.mp4")
    _completed_job(repo, src4k, title="uhd", height=2160, url="https://www.youtube.com/watch?v=cccc")
    uhd = ingest_completed_jobs(repo, store)[0].item
    assert uhd.height == 2160
    assert can_upscale_library_item(uhd) is False
    repo.close()


def test_default_taxonomy_seeded(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    names = {(c.name, c.kind) for c in store.list_collections()}
    for label in SOURCES:
        assert (label, "source") in names
    for label in TYPES:
        assert (label, "type") in names
    for label in SUBJECTS:
        assert (label, "subject") in names
    repo.close()


def test_tag_music_videos_moves_into_folder(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "mv.mp4")
    _completed_job(repo, src, title="MV")
    item = ingest_completed_jobs(repo, store)[0].item
    music = store.get_collection_by_name("Music Videos", KIND_TYPE)
    assert music is not None
    assign_to_collection(repo, store, [item.id], music.id)
    moved = store.get(item.id)
    assert Path(moved.path).parent.name == "Music Videos"
    assert Path(moved.path).is_file()
    tagged = store.list_items(collection_id=music.id)
    assert [t.id for t in tagged] == [item.id]
    repo.close()


def test_custom_collection_and_title_search(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "brand.mp4")
    _completed_job(repo, src, title="Brand Night")
    item = ingest_completed_jobs(repo, store)[0].item
    col = store.create_collection("Brand X")
    assign_to_collection(repo, store, [item.id], col.id)
    assert Path(store.get(item.id).path).parent.name == "Brand X"
    found = store.list_items(search="brand")
    assert len(found) == 1
    repo.close()


def test_favorites_watch_later_and_sort(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    a = ingest_completed_jobs(
        repo, store, [_completed_job(repo, _clip(tmp_path / "dl" / "a.mp4"), title="Alpha", height=480)]
    )[0].item
    ingest_completed_jobs(
        repo, store, [_completed_job(repo, _clip(tmp_path / "dl" / "z.mp4"), title="Zulu", height=1080, url="https://www.youtube.com/watch?v=zzzz")]
    )
    store.set_flags(a.id, is_favorite=True, watch_later=True)
    favs = store.list_items(flag="Favorites")
    assert [i.id for i in favs] == [a.id]
    later = store.list_items(flag="Watch Later")
    assert [i.id for i in later] == [a.id]
    cand = store.list_items(flag="Upscale candidate (≤720p)")
    assert a.id in [i.id for i in cand]
    by_title = store.list_items(sort="title")
    assert [i.title for i in by_title] == ["Alpha", "Zulu"]
    repo.close()


def test_watch_folder_index_only(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    extra = tmp_path / "extra"
    _clip(extra / "outside.mp4")
    store.add_watch_folder(extra, import_mode="index")
    added = index_folder(store, extra)
    assert len(added) == 1
    assert Path(added[0].path).parent == extra.resolve()
    assert (extra / "outside.mp4").is_file()
    repo.close()


def test_remove_metadata_keeps_file(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "keep.mp4")
    _completed_job(repo, src, title="keep")
    item = ingest_completed_jobs(repo, store)[0].item
    path = Path(item.path)
    store.remove_item(item.id)
    assert path.is_file()
    assert store.list_items() == []
    repo.close()


def test_library_tab_label_and_onboarding_dialog(tmp_path: Path):
    import flet as ft

    assert TAB_LABELS[-1] == "Library"
    tabs = build_tabs()
    bar = tabs.content.controls[0]
    assert [t.label for t in bar.tabs][-1] == "Library"
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    assert isinstance(ui.library_grid, ft.GridView)
    src = _clip(tmp_path / "dl" / "ui.mp4")
    _completed_job(repo, src, title="UI clip")
    dlg = ui.on_library_opened()
    assert dlg is not None
    assert dlg.data["step"] == "pick"
    assert ui.library.is_onboarded() is False
    move_dlg = ui.apply_library_root(tmp_path / "Lib")
    assert ui.library.is_onboarded() is False
    assert ui.library.root() is not None
    assert move_dlg is not None
    assert move_dlg.data["step"] == "move"
    assert move_dlg.data["pending"] >= 1
    assert any("UI clip" in t for t in move_dlg.data["sample"])
    ui.confirm_library_move()
    assert ui.library.is_onboarded()
    assert ui.library.list_items()
    dest = Path(ui.library.list_items()[0].path)
    assert dest.is_file()
    assert dest.parent.name == "Uncategorized"
    assert not src.exists()
    assert ui.on_library_opened() is None
    ui.shutdown()


def test_onboarding_skip_keeps_download_files(tmp_path: Path):
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    src = _clip(tmp_path / "dl" / "stay.mp4")
    _completed_job(repo, src, title="Stay")
    ui.apply_library_root(tmp_path / "Lib")
    assert ui.library.is_onboarded() is False
    ui.skip_library_onboarding()
    assert ui.library.is_onboarded()
    assert src.is_file()
    assert ui.library.list_items() == []
    empty = ui.library_empty
    assert empty is not None
    assert "Import" in str(empty.data.get("cta") or empty.content)
    ui.shutdown()


def test_onboarding_resumes_at_move_step(tmp_path: Path):
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.build()
    src = _clip(tmp_path / "dl" / "resume.mp4")
    _completed_job(repo, src, title="Resume me")
    ui.library.set_root(tmp_path / "Lib")
    assert ui.library.is_onboarded() is False
    dlg = ui.on_library_opened()
    assert dlg is not None
    assert dlg.data["step"] == "move"
    assert dlg.data["pending"] >= 1
    ui.shutdown()
