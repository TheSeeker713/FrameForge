"""v0.5.7 — native OS title bar; drag is Windows caption, not WindowDragArea."""

from __future__ import annotations

from pathlib import Path

from tests.flet_fakes import FakePage
from frameforge.ui_flet.theme import COLORS
from frameforge.ui_flet.window_chrome import (
    OPAQUE_BG,
    USE_CUSTOM_TITLE_BAR,
    apply_page_chrome,
    chrome_snapshot,
)


def test_apply_page_chrome_uses_native_title_bar():
    page = FakePage()
    snap = apply_page_chrome(page, set_size=True)
    assert snap["page_bgcolor"] == OPAQUE_BG == COLORS["app_bg"]
    assert snap["window_bgcolor"] == OPAQUE_BG
    assert snap["opacity"] == 1.0
    assert snap["shadow"] is False
    assert snap["title_bar_hidden"] is False
    assert snap["frameless"] is False
    assert snap["custom_title_bar"] is False
    assert USE_CUSTOM_TITLE_BAR is False
    assert "transparent" not in str(snap["page_bgcolor"]).lower()
    assert snap == chrome_snapshot(page)


def test_reapply_does_not_reset_size():
    page = FakePage()
    apply_page_chrome(page, set_size=True)
    page.window.width = 1400
    page.window.height = 800
    apply_page_chrome(page, set_size=False)
    assert page.window.width == 1400
    assert page.window.height == 800
    assert page.window.bgcolor == OPAQUE_BG
    assert page.window.shadow is False
    apply_page_chrome(page, set_size=False)
    assert page.window.title_bar_hidden is False


def test_default_gui_has_no_window_drag_area_and_native_close(tmp_path: Path):
    import flet as ft

    from frameforge.db.repository import JobRepository
    from frameforge.queue.worker import SequentialWorker
    from frameforge.ui_flet.app import FrameForgeUi
    from frameforge.ui_flet.window_chrome import build_custom_title_bar

    bar = build_custom_title_bar(on_close=lambda: None, on_min=lambda: None, on_max=lambda: None)
    assert isinstance(bar, ft.WindowDragArea)

    repo = JobRepository(tmp_path / "w.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    ui.build()
    assert ui.title_bar is None
    ui.page.window.prevent_close = True
    assert ui.handle_window_close() == "choice"
    assert ui.dialogs.kind == "quit"
    ui.minimize_window()
    assert ui.page.window.minimized is True
    ui.toggle_maximize()
    assert ui.page.window.maximized is True
    ui.shutdown()
