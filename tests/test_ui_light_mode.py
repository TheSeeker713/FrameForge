"""D3 — light UI mode: no live thumbs, slower refresh."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.app import TICK_IDLE_MS, TICK_LIGHT_IDLE_MS
from tests.test_tray_service import _FakeIcon


def test_light_mode_slower_refresh_skips_thumbs(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "l.db")
    repo.set_setting("ui_light_mode", "1")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert app._ui_light_mode() is True
        assert app.queue_list._show_thumbs is False
        app.deiconify()
        assert app._next_tick_ms() == TICK_LIGHT_IDLE_MS
        assert TICK_LIGHT_IDLE_MS > TICK_IDLE_MS
        thumbs: list[str] = []
        app.refresh_thumbnails = lambda: thumbs.append("thumbs")  # type: ignore[method-assign]
        app.refresh_queue()
        assert thumbs == []
        repo.set_setting("ui_light_mode", "0")
        app._apply_light_ui()
        assert app._ui_light_mode() is False
        assert app.queue_list._show_thumbs is True
        assert app._next_tick_ms() == TICK_IDLE_MS
    finally:
        app._shutting_down = True
        app._cancel_tick()
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
