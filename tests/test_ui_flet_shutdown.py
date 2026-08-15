"""v0.5.4 — X / Ctrl+Q always open a quit dialog; Force quit always available."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from frameforge.db.repository import JobRepository
from frameforge.gui.exit_policy import CHOICE_FORCE_QUIT, CHOICE_QUIT_IDLE, CHOICE_STAY
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.flet_fakes import FakePage


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "s.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_idle_close_opens_confirm_not_silent_exit(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.page.window.prevent_close = True
    assert ui.exit_process_on_quit is False
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    assert ui._shutdown_complete is False
    action_blob = " ".join(str(getattr(a, "content", a)) for a in ui.quit_dialog.actions)
    assert "Quit" in action_blob
    assert "Force quit now" in action_blob
    assert "Stay" in action_blob
    ui.quit_dialog.data["on_choice"](CHOICE_QUIT_IDLE)
    assert ui._shutdown_complete is True
    assert ui.page.window.prevent_close is False


def test_busy_quit_offers_force_and_stay(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    assert ui.handle_window_close() == "choice"
    labels = []
    for tile in ui.quit_dialog.content.controls:
        title = getattr(tile, "title", None)
        labels.append(getattr(title, "value", "") or str(title))
    blob = " ".join(labels)
    assert "Cancel download" in blob
    assert "Pause download" in blob
    actions = " ".join(str(getattr(a, "content", a)) for a in ui.quit_dialog.actions)
    assert "Force quit now" in actions
    assert "Stay" in actions
    ui.quit_dialog.data["on_choice"](CHOICE_STAY)
    assert ui._shutdown_complete is False
    ui.shutdown()


def test_force_quit_path_callable_without_os_exit(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.page.window.prevent_close = True
    ui.force_quit()
    assert ui._shutdown_complete is True
    assert ui.page.window.prevent_close is False
    assert ui._watchdog_armed is True


def test_second_close_force_quits(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    assert ui.handle_window_close() == "choice"
    assert ui.handle_window_close() == "force"
    assert ui._shutdown_complete is True


def test_quit_dialog_failure_still_force_quits(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()

    def boom() -> None:
        raise RuntimeError("modal failed")

    ui.open_quit_dialog = boom  # type: ignore[method-assign]
    assert ui.handle_window_close() == "exit"
    assert ui._shutdown_complete is True


def test_stay_resets_close_click_so_next_x_is_dialog(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    assert ui.handle_window_close() == "choice"
    ui.quit_dialog.data["on_choice"](CHOICE_STAY)
    assert ui._shutdown_complete is False
    assert ui.handle_window_close() == "choice"
    assert ui._shutdown_complete is False
def test_ctrl_q_enters_quit_flow(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui._on_keyboard(SimpleNamespace(key="Q", ctrl=True))
    assert ui.dialogs.kind == "quit"
    ui.shutdown()


def test_async_destroy_is_awaited_without_runtimewarning(tmp_path: Path):
    import warnings

    from frameforge.ui_flet.window_teardown import request_window_destroy

    ui = _ui(tmp_path)
    ui.page = FakePage()
    called = {"n": 0}

    async def adestroy() -> None:
        called["n"] += 1
        ui.page.window.destroyed = True

    ui.page.window.destroy = adestroy
    ui.page.window.close = adestroy
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        status = request_window_destroy(ui.page, wait=1)
    assert called["n"] == 1
    assert status in {"awaited", "scheduled", "sync"}
    assert ui.page.window.destroyed is True
    assert not any("never awaited" in str(x.message).lower() for x in rec)
    ui.shutdown()


def test_force_quit_invokes_window_destroy(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.force_quit()
    assert ui._shutdown_complete is True
    assert ui.page.window.destroyed is True
    assert ui.last_destroy_status in {"awaited", "scheduled", "sync"}
