"""v0.5.3 — clear finished scope + undo restores visibility only."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.bridge import UiBridge


def _bridge(tmp_path: Path) -> UiBridge:
    repo = JobRepository(tmp_path / "u.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return UiBridge(repo, worker)


def test_clear_finished_mixed_queue_keeps_pending(tmp_path: Path):
    b = _bridge(tmp_path)
    pending = b.enqueue_url("https://example.com/p")
    done = b.enqueue_url("https://example.com/ok")
    failed = b.enqueue_url("https://example.com/bad")
    b.repo.update_status(done.id, "completed", progress=100)
    annotate_job_error(b.repo, failed.id, "nope")
    ids = b.clear_finished()
    assert set(ids) == {done.id, failed.id}
    visible = {j.id: j.status for j in b.repo.list_jobs()}
    assert visible[pending.id] == "pending"
    assert done.id not in visible
    assert failed.id not in visible
    assert b.repo.get(pending.id).queue_hidden is False
    b.repo.close()


def test_undo_restores_clear_finished_visibility(tmp_path: Path):
    b = _bridge(tmp_path)
    pending = b.enqueue_url("https://example.com/p")
    done = b.enqueue_url("https://example.com/ok")
    b.repo.update_status(done.id, "completed", progress=100)
    b.clear_finished()
    assert done.id not in {j.id for j in b.repo.list_jobs()}
    assert "Cleared 1 item" in (b.last_clear_message or "")
    n = b.undo_clear()
    assert n == 1
    visible = {j.id: j.status for j in b.repo.list_jobs()}
    assert visible[pending.id] == "pending"
    assert visible[done.id] == "completed"
    assert b.repo.get(done.id).queue_hidden is False
    assert b.last_clear_message is None
    b.repo.close()


def test_undo_restores_clear_selected_pending(tmp_path: Path):
    b = _bridge(tmp_path)
    keep = b.enqueue_url("https://example.com/keep")
    drop = b.enqueue_url("https://example.com/drop")
    b.clear_selected([drop.id])
    assert drop.id not in {j.id for j in b.repo.list_jobs()}
    assert keep.id in {j.id for j in b.repo.list_jobs()}
    b.undo_clear()
    assert {j.id for j in b.repo.list_jobs()} == {keep.id, drop.id}
    b.repo.close()


def test_flet_clear_finished_banner_and_undo(tmp_path: Path):
    repo = JobRepository(tmp_path / "f.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    pending = ui.bridge.enqueue_url("https://example.com/p")
    done = ui.bridge.enqueue_url("https://example.com/ok")
    ui.repo.update_status(done.id, "completed", progress=100)
    ui.build()
    ui.clear_finished()
    assert pending.id in {j.id for j in ui.queue_jobs()}
    assert done.id not in {j.id for j in ui.queue_jobs()}
    assert ui.undo_banner is not None and ui.undo_banner.visible is True
    assert ui.queue_chrome.data.get("show_undo") is True
    ui.undo_clear()
    assert done.id in {j.id for j in ui.queue_jobs()}
    assert ui.undo_banner.visible is False
    ui.shutdown()
