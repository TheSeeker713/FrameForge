"""v0.5.3 — close must always tear down; second close forces kill."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.flet_fakes import FakePage


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "s.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_idle_close_releases_prevent_close_and_arms_watchdog_flag(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.page.window.prevent_close = True
    assert ui.exit_process_on_quit is False
    assert ui.handle_window_close() == "exit"
    assert ui._shutdown_complete is True
    assert ui.page.window.prevent_close is False
    assert ui._watchdog_armed is True
    assert ui._exiting is True


def test_busy_close_then_second_close_forces_exit(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    assert ui._shutdown_complete is False
    assert ui.handle_window_close() == "force"
    assert ui._shutdown_complete is True
    assert ui.page.window.prevent_close is False


def test_quit_busy_failure_still_exits(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")

    def boom() -> None:
        raise RuntimeError("modal failed")

    ui.open_quit_busy = boom  # type: ignore[method-assign]
    assert ui.handle_window_close() == "exit"
    assert ui._shutdown_complete is True


def test_watchdog_timer_not_started_in_pytest(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.handle_window_close()
    assert ui.exit_process_on_quit is False
    assert ui._watchdog_armed is True
