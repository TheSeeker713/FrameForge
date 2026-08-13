"""Flet desktop shell — light FrameForge window (Phase A2 placeholders)."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.ui_flet.theme import (
    COLORS,
    FONT_FAMILY,
    TAB_LABELS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)


def apply_page_chrome(page: ft.Page) -> None:
    page.title = "FrameForge"
    page.bgcolor = COLORS["app_bg"]
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.theme = ft.Theme(font_family=FONT_FAMILY, color_scheme_seed=COLORS["accent"])
    window = getattr(page, "window", None)
    if window is not None:
        window.width = WINDOW_WIDTH
        window.height = WINDOW_HEIGHT
        window.min_width = 900
        window.min_height = 600


def _placeholder_panel(label: str) -> ft.Container:
    return ft.Container(
        expand=True,
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=12,
        padding=24,
        content=ft.Text(
            f"{label} placeholder",
            color=COLORS["text_secondary"],
            size=14,
        ),
    )


def build_header() -> ft.Row:
    return ft.Row(
        [
            ft.Text(
                "FrameForge",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=COLORS["text_primary"],
            ),
            ft.Container(expand=True),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor=COLORS["surface"],
                border=ft.Border.all(1, COLORS["border"]),
                border_radius=999,
                content=ft.Text("Idle • 0 ready", color=COLORS["text_secondary"], size=13),
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def build_tabs() -> ft.Tabs:
    views = [_placeholder_panel(name) for name in TAB_LABELS]
    return ft.Tabs(
        length=len(TAB_LABELS),
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[ft.Tab(label=name) for name in TAB_LABELS],
                    label_color=COLORS["accent"],
                    unselected_label_color=COLORS["text_secondary"],
                    indicator_color=COLORS["accent"],
                    divider_color=COLORS["border"],
                ),
                ft.TabBarView(expand=True, controls=views),
            ],
        ),
    )


def build_shell() -> ft.Column:
    """Empty light chrome: header + Queue/History/Thumbnails placeholders."""
    return ft.Column(
        expand=True,
        spacing=16,
        controls=[build_header(), build_tabs()],
    )


def main(page: ft.Page) -> None:
    apply_page_chrome(page)
    page.add(build_shell())


def run_gui(**kwargs: Any) -> None:
    ft.app(main, **kwargs)
