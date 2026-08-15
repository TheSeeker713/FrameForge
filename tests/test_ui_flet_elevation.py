"""Phase A — widget hover elevation without OS window shadow."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.ui_flet.app import apply_page_chrome, build_hero
from frameforge.ui_flet.components.job_card import build_floating_bar, build_job_card, build_queue_chrome
from frameforge.ui_flet.elevation import (
    ELEVATION_HOVER,
    ELEVATION_REST,
    elevated_filled_button,
    elevated_outlined_button,
    filled_button_style,
)
from frameforge.ui_flet.queue_chrome import queue_chrome_spec
from frameforge.ui_flet.theme import COLORS
from tests.flet_fakes import FakePage


def test_elevation_hover_is_deeper_than_rest():
    assert ELEVATION_HOVER["blur_radius"] > ELEVATION_REST["blur_radius"]
    assert ELEVATION_HOVER["offset"][1] > ELEVATION_REST["offset"][1]


def test_job_card_and_overflow_have_hover_specs(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    job = repo.enqueue("https://example.com/v", title="clip")
    card = build_job_card(job, selected=False, expanded=False, show_progress=False)
    spec = (card.data or {})["elevation"]
    assert spec["hover"]["blur_radius"] > spec["rest"]["blur_radius"]
    assert card.shadow is not None
    assert card.on_hover is not None
    row = card.content.controls[0]
    overflow = row.controls[-1]
    assert (overflow.data or {}).get("elevation")
    assert overflow.on_hover is not None
    repo.close()


def test_selected_card_keeps_tint_and_shadow(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    job = repo.enqueue("https://example.com/s", title="sel")
    card = build_job_card(job, selected=True, expanded=False, show_progress=False)
    assert card.bgcolor == COLORS["select"]
    assert card.shadow is not None
    assert card.data["elevation"]["rest"]["blur_radius"] >= ELEVATION_REST["blur_radius"]
    repo.close()


def test_filled_and_outlined_buttons_have_state_elevation():
    filled = elevated_filled_button("Go")
    el = filled.style.elevation
    assert el[ft.ControlState.HOVERED] > el[ft.ControlState.DEFAULT]
    assert el[ft.ControlState.PRESSED] < el[ft.ControlState.HOVERED]
    assert el[ft.ControlState.DISABLED] == 0
    outline = elevated_outlined_button("More")
    assert outline.style.elevation[ft.ControlState.HOVERED] > outline.style.elevation[ft.ControlState.DISABLED]
    dead = elevated_outlined_button("Nope", disabled=True)
    assert dead.disabled is True
    assert dead.data["elevation"] is None


def test_hero_and_chrome_use_elevated_buttons():
    hero = build_hero()
    add = hero.data["add"]
    imp = hero.data["import"]
    assert isinstance(add, ft.FilledButton)
    assert add.style.elevation[ft.ControlState.HOVERED] > add.style.elevation[ft.ControlState.DEFAULT]
    assert isinstance(imp, ft.OutlinedButton)
    spec = queue_chrome_spec(
        [type("J", (), {"status": "pending", "id": 1})()],
        set(),
    )
    chrome = build_queue_chrome(spec)
    assert chrome.data["elevation"]["hover"]["blur_radius"] > chrome.data["elevation"]["rest"]["blur_radius"]
    bar = build_floating_bar(
        {
            "count": 1,
            "show_download": True,
            "show_upscale": False,
            "show_convert": False,
            "show_clear": True,
            "show_retry": False,
            "more_items": ["clear_selected"],
        }
    )
    assert bar.data["elevation"]["hover"]["blur_radius"] > bar.data["elevation"]["rest"]["blur_radius"]
    download = bar.content.controls[2]
    assert isinstance(download, ft.FilledButton)
    assert download.style is not None


def test_window_chrome_forbids_os_shadow_after_elevation():
    page = FakePage()
    apply_page_chrome(page)
    assert page.window.bgcolor == COLORS["app_bg"]
    assert page.window.shadow is False
    assert page.window.opacity == 1.0
    assert page.window.title_bar_hidden is True
    style = filled_button_style()
    assert style.elevation[ft.ControlState.HOVERED] >= 3
