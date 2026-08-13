"""Step 1.3 — Clear selected / Clear finished GUI enablement and actions."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.actions import can_clear_from_queue
from tests.test_tray_service import _FakeIcon


def test_can_clear_from_queue_skips_active():
    from types import SimpleNamespace

    assert can_clear_from_queue(SimpleNamespace(status="pending")) is True
    assert can_clear_from_queue(SimpleNamespace(status="completed")) is True
    assert can_clear_from_queue(SimpleNamespace(status="failed")) is True
    assert can_clear_from_queue(SimpleNamespace(status="paused")) is True
    assert can_clear_from_queue(SimpleNamespace(status="downloading")) is False
    assert can_clear_from_queue(SimpleNamespace(status="upscaling")) is False
    assert can_clear_from_queue(SimpleNamespace(status="converting")) is False


def test_clear_buttons_enablement_and_actions(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    pending = repo.enqueue("https://example.com/p", title="p")
    done = repo.enqueue("https://example.com/d", title="d")
    failed = repo.enqueue("https://example.com/f", title="f")
    repo.update_status(done.id, "completed", progress=100)
    repo.update_status(failed.id, "failed", error="x")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        app.refresh_queue()
        assert str(app.clear_finished_btn.cget("state")) == "normal"
        app.queue_list.set_selected(set())
        app._selected_ids = set()
        app._sync_clear_buttons()
        assert str(app.clear_selected_btn.cget("state")) == "disabled"

        app.queue_list.set_selected({pending.id})
        app._selected_ids = {pending.id}
        app._sync_clear_buttons()
        assert str(app.clear_selected_btn.cget("state")) == "normal"

        active = repo.enqueue("https://example.com/dl")
        repo.update_status(active.id, "downloading", progress=3)
        app.refresh_queue()
        app.queue_list.set_selected({active.id})
        app._selected_ids = {active.id}
        app._sync_clear_buttons()
        assert str(app.clear_selected_btn.cget("state")) == "disabled"

        app.queue_list.set_selected({pending.id})
        app._selected_ids = {pending.id}
        app.clear_selected_from_queue()
        visible = {j.id for j in repo.list_jobs()}
        assert pending.id not in visible
        assert done.id in visible

        app._ask_clear_finished = lambda: True
        app.clear_finished_from_queue()
        visible = {j.id for j in repo.list_jobs()}
        assert done.id not in visible
        assert failed.id not in visible
        assert active.id in visible
        hist = {j.id for j in repo.list_history()}
        assert done.id in hist
        assert failed.id in hist
        assert str(app.clear_finished_btn.cget("state")) == "disabled"
    finally:
        app._shutting_down = True
        app._cancel_tick()
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
