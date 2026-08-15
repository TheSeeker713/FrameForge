"""v0.5.3 — opaque chrome flags; reapply must not reset size."""

from __future__ import annotations

from tests.flet_fakes import FakePage
from frameforge.ui_flet.theme import COLORS
from frameforge.ui_flet.window_chrome import OPAQUE_BG, apply_page_chrome, chrome_snapshot


def test_apply_page_chrome_is_fully_opaque():
    page = FakePage()
    snap = apply_page_chrome(page, set_size=True)
    assert snap["page_bgcolor"] == OPAQUE_BG == COLORS["app_bg"]
    assert snap["window_bgcolor"] == OPAQUE_BG
    assert snap["opacity"] == 1.0
    assert snap["shadow"] is False
    assert snap["title_bar_hidden"] is False
    assert snap["frameless"] is False
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
