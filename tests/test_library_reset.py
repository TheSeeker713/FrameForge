"""Reset Library onboarding without deleting media."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.ingest import ingest_completed_jobs
from frameforge.library.reset import reset_library_state
from frameforge.library.store import LibraryStore
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.flet_fakes import FakePage
from tests.test_library import _clip, _completed_job, _repo


def test_reset_library_clears_index_keeps_files(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "keep.mp4")
    _completed_job(repo, src, title="keep")
    item = ingest_completed_jobs(repo, store)[0].item
    media = Path(item.path)
    assert media.is_file()
    assert store.is_onboarded()
    reset_library_state(store)
    assert store.is_onboarded() is False
    assert store.root() is None
    assert store.onboarding_step() == "pick"
    assert store.list_items() == []
    assert media.is_file()
    assert store.list_collections()
    repo.close()


def test_ui_reset_library_reopens_onboarding(tmp_path: Path):
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.build()
    ui.library.complete_onboarding(tmp_path / "Lib")
    dlg = ui.open_reset_library()
    assert dlg.data["kind"] == "reset_library"
    ui.confirm_reset_library()
    assert ui.library.is_onboarded() is False
    assert ui.library.root() is None
    assert ui.dialogs.kind == "library_onboard"
    ui.shutdown()


def test_reset_reverts_missing_uncategorized_job_paths(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    lib = store.complete_onboarding(tmp_path / "Lib")
    youtube = _clip(tmp_path / "youtube" / "clip [dQw4w9WgXcQ].mp4")
    missing = Path(lib) / "Uncategorized" / "clip [dQw4w9WgXcQ].mp4"
    job = _completed_job(repo, youtube, title="clip")
    repo.set_paths(job.id, download_path=str(missing), output_path=str(missing))
    reset_library_state(store, download_roots=[tmp_path / "youtube"])
    loaded = repo.get(job.id)
    assert Path(loaded.download_path).resolve() == youtube.resolve()
    assert youtube.is_file()
    repo.close()


def test_settings_dismiss_does_not_close_reset_dialog(tmp_path: Path):
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    ui.build()
    ui.open_settings()
    assert ui.dialogs.kind == "settings"
    settings = ui.dialogs.current
    assert settings is not None
    stale_dismiss = settings.on_dismiss
    ui.open_reset_library()
    assert ui.dialogs.kind == "reset_library"
    assert ui.dialogs.current is not None
    assert ui.dialogs.current.data.get("kind") == "reset_library"
    if callable(stale_dismiss):
        stale_dismiss()
    assert ui.dialogs.kind == "reset_library"
    ui.dialogs.close(kind="settings")
    assert ui.dialogs.kind == "reset_library"
    ui.shutdown()


def test_library_new_replace_keeps_onboard_after_stale_dismiss(tmp_path: Path):
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    ui.build()
    ui.apply_library_root(tmp_path / "Lib")
    _completed_job(ui.repo, _clip(tmp_path / "dl" / "a.mp4"), title="a")
    ui._library_scan_roots = [tmp_path / "dl"]
    new_dlg = ui.open_library_new_files()
    assert ui.dialogs.kind == "library_new"
    stale = getattr(new_dlg, "on_dismiss", None) if new_dlg is not None else None
    ui.open_library_onboarding()
    assert ui.dialogs.kind == "library_onboard"
    if callable(stale):
        stale()
    assert ui.dialogs.kind == "library_onboard"
    ui.shutdown()


def test_reset_library_state_script_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts" / "reset_library.ps1").is_file()
    assert (root / "scripts" / "reset_library_state.ps1").is_file()
