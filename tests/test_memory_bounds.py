"""D1 — bound worker event log and error-panel text."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.gui.app import ERROR_PANEL_MAX_CHARS
from frameforge.queue.worker import MAX_WORKER_EVENTS, SequentialWorker


def test_worker_events_bounded(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    for i in range(MAX_WORKER_EVENTS + 50):
        worker._record_event(1, "download_start")
    assert len(worker.events) == MAX_WORKER_EVENTS
    assert worker.events[0].stage == "download_start"
    repo.close()


def test_error_panel_text_truncated(tmp_path: Path):
    import pytest

    from tests.test_tray_service import _FakeIcon

    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "p.db")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        huge = "x" * (ERROR_PANEL_MAX_CHARS + 200)
        app._set_error_panel_text(huge)
        shown = app.error_panel.get("1.0", "end-1c")
        assert len(shown) <= ERROR_PANEL_MAX_CHARS + 5
        assert shown.endswith("…")
    finally:
        app._shutting_down = True
        app._cancel_tick()
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
