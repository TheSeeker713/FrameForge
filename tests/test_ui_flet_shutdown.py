"""v0.5.8 — X → Quit/Cancel confirm; process + Flet View actually exit."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.flet_fakes import FakePage


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "s.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def _action_blob(dlg) -> str:
    return " ".join(str(getattr(a, "content", a)) for a in dlg.actions)


def test_idle_close_opens_simple_confirm(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.page.window.prevent_close = True
    assert ui.exit_process_on_quit is False
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    assert ui._shutdown_complete is False
    blob = _action_blob(ui.quit_dialog)
    assert "Quit" in blob
    assert "Cancel" in blob
    assert "Force quit" not in blob
    assert "Stay" not in blob
    ui.quit_dialog.data["on_quit"]()
    assert ui._shutdown_complete is True
    assert ui.page.window.prevent_close is False


def test_busy_quit_is_still_quit_or_cancel(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    assert ui.handle_window_close() == "choice"
    body = str(getattr(ui.quit_dialog.content, "value", ui.quit_dialog.content))
    assert "in progress" in body.lower()
    blob = _action_blob(ui.quit_dialog)
    assert "Quit" in blob
    assert "Cancel" in blob
    assert "Force quit" not in blob
    assert "Cancel download" not in blob
    ui.quit_dialog.data["on_cancel"]()
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


def test_duplicate_close_event_keeps_confirm(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    assert ui.handle_window_close() == "choice"
    assert ui.handle_window_close() == "choice"
    assert ui._shutdown_complete is False
    ui.shutdown()


def test_second_close_after_debounce_quits(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    job = ui.repo.enqueue("https://example.com/live")
    ui.repo.update_status(job.id, "downloading")
    assert ui.handle_window_close() == "choice"
    ui._last_close_event = 0.0
    assert ui.handle_window_close() == "quit"
    assert ui._shutdown_complete is True


def test_quit_dialog_failure_still_quits(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()

    def boom() -> None:
        raise RuntimeError("modal failed")

    ui.open_quit_dialog = boom  # type: ignore[method-assign]
    assert ui.handle_window_close() == "quit"
    assert ui._shutdown_complete is True


def test_cancel_resets_so_next_x_is_dialog(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    assert ui.handle_window_close() == "choice"
    ui.quit_dialog.data["on_cancel"]()
    assert ui._shutdown_complete is False
    assert ui.handle_window_close() == "choice"
    assert ui._shutdown_complete is False
    ui.shutdown()


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


def test_commit_quit_invokes_window_destroy_without_waiting(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui._commit_quit()
    assert ui._shutdown_complete is True
    assert ui.page.window.destroyed is True
    assert ui.last_destroy_status in {"awaited", "scheduled", "sync"}
    assert ui.page.window.prevent_close is False


def test_watchdog_uses_hard_exit_not_bare_os_exit():
    from frameforge.ui_flet import app as app_mod

    src = Path(app_mod.__file__).read_text(encoding="utf-8")
    assert "schedule_hard_exit" in src
    assert "lambda: os._exit" not in src
