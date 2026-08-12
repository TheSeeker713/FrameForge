"""C2 — idle vs active GUI timer; skip queue work when withdrawn; cancel on shutdown."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.app import TICK_ACTIVE_MS, TICK_IDLE_MS, TICK_TRAY_MS
from tests.test_tray_service import _FakeIcon


def test_tick_intervals_idle_slower_than_active():
    assert TICK_IDLE_MS > TICK_ACTIVE_MS
    assert TICK_IDLE_MS >= 2000
    assert TICK_ACTIVE_MS <= 500
    assert TICK_TRAY_MS >= TICK_ACTIVE_MS


def test_tick_skips_queue_refresh_when_withdrawn(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "t.db")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert app._window_withdrawn() is True
        assert app._next_tick_ms() == TICK_TRAY_MS
        calls: list[str] = []
        app.refresh_queue = lambda **_k: calls.append("full")  # type: ignore[method-assign]
        app.refresh_progress = lambda: calls.append("prog")  # type: ignore[method-assign]
        app._poll_resources = lambda: None  # type: ignore[method-assign]
        app._tick()
        assert calls == []
        app.deiconify()
        assert app._window_withdrawn() is False
        assert app._next_tick_ms() == TICK_IDLE_MS
        app.worker._armed.set()
        assert app._next_tick_ms() == TICK_ACTIVE_MS
        app._tick()
        assert "prog" in calls
        assert "full" not in calls
    finally:
        app._shutting_down = True
        app._cancel_tick()
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()


def test_shutdown_cancels_tick_timer(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "s.db")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert app._tick_after_id is not None
        app.shutdown()
        assert app._tick_after_id is None
    finally:
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
