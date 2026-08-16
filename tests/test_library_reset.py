"""Reset Library onboarding without deleting media."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.ingest import ingest_completed_jobs
from frameforge.library.reset import reset_library_state
from frameforge.library.store import LibraryStore
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
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
