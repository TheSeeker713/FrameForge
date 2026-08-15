"""v0.5.9 — cancelled/failed resume to pending without auto-start."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.errors import annotate_job_error
from frameforge.gui.actions import can_download, can_retry_download
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.job_view import more_menu_items, overflow_actions


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "r.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_cancelled_overflow_and_selection_resume_to_pending(tmp_path: Path):
    ui = _ui(tmp_path)
    cancelled = ui.bridge.enqueue_url("https://example.com/c", title="c")
    ui.repo.update_status(cancelled.id, "cancelled", progress=40)
    failed = ui.bridge.enqueue_url("https://example.com/f", title="f")
    annotate_job_error(ui.repo, failed.id, "Downloaded file not found for https://example.com/f")
    assert can_retry_download(ui.repo.get(cancelled.id)) is True
    assert can_download(ui.repo.get(cancelled.id)) is False
    assert "retry" in overflow_actions(ui.repo.get(cancelled.id))
    ui.selected_ids = {cancelled.id, failed.id}
    items = more_menu_items(ui.queue_jobs(), ui.selected_ids)
    assert "retry_selected" in items
    ids = ui.bridge.queue_again([cancelled.id, failed.id])
    assert set(ids) == {cancelled.id, failed.id}
    assert ui.worker.is_armed is False
    assert ui.repo.get(cancelled.id).status == "pending"
    assert ui.repo.get(failed.id).status == "pending"
    assert ui.repo.get(cancelled.id).progress == 40
    assert can_download(ui.repo.get(cancelled.id)) is True
    ui.shutdown()


def test_download_all_pending_skips_cancelled_until_resumed(tmp_path: Path):
    ui = _ui(tmp_path)
    cancelled = ui.bridge.enqueue_url("https://example.com/c")
    ui.repo.update_status(cancelled.id, "cancelled")
    pending = ui.bridge.enqueue_url("https://example.com/p")
    ui.bridge.download_all_pending()
    assert pending.id in (ui.worker._only_ids or set()) or ui.worker.is_armed
    assert ui.repo.get(cancelled.id).status == "cancelled"
    ui.shutdown()
