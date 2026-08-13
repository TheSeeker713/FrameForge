"""Phase A2 — Flet is installed and the light shell can be built without a window."""

from __future__ import annotations

import flet as ft
from PIL import Image

from frameforge.ui_flet.app import apply_page_chrome, build_header, build_shell, build_tabs
from frameforge.ui_flet.theme import COLORS, TAB_LABELS


def test_flet_and_pillow_import():
    assert ft.__version__.startswith("0.86")
    assert Image is not None


def test_locked_light_tokens():
    assert COLORS["app_bg"] == "#F8FAFC"
    assert COLORS["surface"] == "#FFFFFF"
    assert COLORS["border"] == "#E2E8F0"
    assert COLORS["text_primary"] == "#0F172A"
    assert COLORS["text_secondary"] == "#64748B"
    assert COLORS["accent"] == "#2563EB"
    assert COLORS["select"] == "#EFF6FF"
    assert COLORS["progress"] == "#3B82F6"
    assert COLORS["success"] == "#10B981"
    assert COLORS["success_bg"] == "#ECFDF5"
    assert COLORS["danger"] == "#EF4444"
    assert COLORS["danger_bg"] == "#FEF2F2"


def test_shell_header_and_tab_placeholders():
    header = build_header()
    titles = [c.value for c in header.controls if isinstance(c, ft.Text)]
    assert "FrameForge" in titles
    tabs = build_tabs()
    bar = tabs.content.controls[0]
    labels = [t.label for t in bar.tabs]
    assert tuple(labels) == TAB_LABELS
    shell = build_shell()
    assert len(shell.controls) == 2
    apply_page_chrome  # imported for C2 wiring; construction is side-effect free
