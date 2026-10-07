"""Library Select all enables bulk remove / delete / collection actions."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.ingest import ingest_completed_jobs
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.test_library import _clip, _completed_job, _repo


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    return ui


def test_select_all_library_selects_visible_and_enables_bulk(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    for i, name in enumerate(("one", "two", "three")):
        src = _clip(tmp_path / "dl" / f"{name}.mp4")
        _completed_job(ui.repo, src, title=name, url=f"https://www.youtube.com/watch?v={name}{i}")
    ingest_completed_jobs(ui.repo, ui.library)
    ui.refresh_library()
    assert ui.library_visible_count == 3
    assert ui.library_selected_ids == set()

    ui.select_all_library()
    assert ui.library_selected_ids == set(ui._library_visible_ids)
    assert len(ui.library_selected_ids) == 3
    toolbar = ui.library_toolbar
    assert toolbar is not None
    assert toolbar.data["selected_count"] == 3
    row = toolbar.controls[0]
    select_btn = row.data["select_all"]
    assert select_btn.data["kind"] == "select_all"
    assert select_btn.data["all_selected"] is True
    assert select_btn.disabled is False
    assert row.data["add"].disabled is False

    dlg = ui.confirm_library_remove(delete_files=False)
    assert dlg is not None
    ui.apply_library_remove(delete_files=False)
    assert ui.library.list_items() == []
    assert ui.library_selected_ids == set()
    ui.shutdown()


def test_clear_library_selection(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.library.complete_onboarding(tmp_path / "Lib")
    src = _clip(tmp_path / "dl" / "clip.mp4")
    _completed_job(ui.repo, src, title="clip")
    ingest_completed_jobs(ui.repo, ui.library)
    ui.refresh_library()
    ui.select_all_library()
    assert ui.library_selected_ids
    ui.clear_library_selection()
    assert ui.library_selected_ids == set()
    assert ui.library_toolbar.data["selected_count"] == 0
    ui.shutdown()


def test_select_all_queue(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.repo.enqueue("https://www.youtube.com/watch?v=aaa", title="a")
    ui.repo.enqueue("https://www.youtube.com/watch?v=bbb", title="b")
    ui.refresh_queue(force=True)
    ui.select_all_queue()
    assert ui.selected_ids == {j.id for j in ui.queue_jobs()}
    assert len(ui.selected_ids) == 2
    ui.shutdown()
