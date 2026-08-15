"""FrameForge window chrome — native OS title bar (reliable drag)."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge import __version__
from frameforge.ui_flet.theme import COLORS, FONT_FAMILY, WINDOW_HEIGHT, WINDOW_WIDTH

# 6-digit hex only — never None, never 8-digit alpha, never "transparent".
OPAQUE_BG = COLORS["app_bg"]
TITLE_BAR_HEIGHT = 36
# Custom WindowDragArea is gated off. Native caption is the drag surface (PASS).
USE_CUSTOM_TITLE_BAR = False


def chrome_snapshot(page: Any) -> dict[str, Any]:
    """Runtime flags the user/agent can log when drag still fails."""
    win = getattr(page, "window", None)
    return {
        "page_bgcolor": getattr(page, "bgcolor", None),
        "window_bgcolor": getattr(win, "bgcolor", None) if win is not None else None,
        "opacity": getattr(win, "opacity", None) if win is not None else None,
        "shadow": getattr(win, "shadow", None) if win is not None else None,
        "title_bar_hidden": getattr(win, "title_bar_hidden", None) if win is not None else None,
        "title_bar_buttons_hidden": getattr(win, "title_bar_buttons_hidden", None)
        if win is not None
        else None,
        "frameless": getattr(win, "frameless", None) if win is not None else None,
        "visible": getattr(win, "visible", None) if win is not None else None,
        "ignore_mouse_events": getattr(win, "ignore_mouse_events", None) if win is not None else None,
        "transparent": getattr(win, "transparent", None) if win is not None else None,
        "custom_title_bar": bool(USE_CUSTOM_TITLE_BAR),
    }


def apply_page_chrome(page: ft.Page, *, set_size: bool = True) -> dict[str, Any]:
    """Opaque fill + native OS title bar. Drag is the Windows caption, not WindowDragArea.

    ``set_size`` only on first attach — reapplying width/height during drag fights the user.
    Never calls DWM or the process foreground-window API. See SHELL_SAFETY.md.
    """
    page.title = f"FrameForge {__version__}"
    page.bgcolor = OPAQUE_BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = ft.Padding.all(20)
    page.theme = ft.Theme(font_family=FONT_FAMILY, color_scheme_seed=COLORS["accent"])
    if hasattr(page, "decoration"):
        try:
            page.decoration = None
        except Exception:  # noqa: BLE001
            pass
    window = getattr(page, "window", None)
    if window is not None:
        if set_size:
            window.width = WINDOW_WIDTH
            window.height = WINDOW_HEIGHT
            window.min_width = 900
            window.min_height = 600
        window.bgcolor = OPAQUE_BG
        window.opacity = 1.0
        window.shadow = False
        window.title_bar_hidden = bool(USE_CUSTOM_TITLE_BAR)
        if hasattr(window, "title_bar_buttons_hidden"):
            window.title_bar_buttons_hidden = bool(USE_CUSTOM_TITLE_BAR)
        window.frameless = False
        if hasattr(window, "transparent"):
            window.transparent = False
        if getattr(window, "ignore_mouse_events", False):
            window.ignore_mouse_events = False
    return chrome_snapshot(page)


def build_custom_title_bar(
    *,
    on_close: Any,
    on_min: Any | None = None,
    on_max: Any | None = None,
    on_drag_start: Any | None = None,
    on_drag_end: Any | None = None,
) -> ft.WindowDragArea:
    """Gated helper. Default GUI does not use this — native caption is the drag surface."""
    min_btn = ft.IconButton(
        icon=ft.Icons.REMOVE,
        tooltip="Minimize",
        icon_color=COLORS["text_primary"],
        icon_size=18,
        on_click=lambda _e=None: on_min and on_min(),
    )
    max_btn = ft.IconButton(
        icon=ft.Icons.CROP_SQUARE,
        tooltip="Maximize",
        icon_color=COLORS["text_primary"],
        icon_size=18,
        on_click=lambda _e=None: on_max and on_max(),
    )
    close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        tooltip="Close",
        icon_color=COLORS["danger"],
        icon_size=18,
        on_click=lambda _e=None: on_close and on_close(),
    )
    row = ft.Container(
        height=TITLE_BAR_HEIGHT,
        bgcolor=OPAQUE_BG,
        padding=ft.Padding.symmetric(horizontal=8),
        content=ft.Row(
            [
                ft.Text(
                    f"FrameForge {__version__}",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=COLORS["text_primary"],
                ),
                ft.Container(expand=True),
                min_btn,
                max_btn,
                close_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        data={"min": min_btn, "max": max_btn, "close": close_btn},
    )
    area = ft.WindowDragArea(
        content=row,
        maximizable=True,
        on_drag_start=on_drag_start,
        on_drag_end=on_drag_end,
    )
    area.data = row.data
    return area


def frameforge_native_hwnd(page: Any | None) -> int | None:
    """Return the FrameForge/Flet window HWND only.

    Never uses the process foreground window (that is how Explorer was restyled).
    Unknown handle → None (callers must no-op).
    """
    if page is None:
        return None
    win = getattr(page, "window", None)
    if win is None:
        return None
    for attr in ("native_id", "hwnd", "handle"):
        val = getattr(win, attr, None)
        if isinstance(val, int) and val != 0:
            return val
    return None


def disable_dwm_glass(page: Any | None = None) -> str:
    """Do not mutate DWM, Explorer, or session themes.

    Historical bug: this used the foreground window plus DWM attributes,
    which restyled File Explorer when it was focused during chrome ticks.
    FrameForge chrome is Flet-only (page/window properties). Returns ``noop``.
    """
    _ = frameforge_native_hwnd(page)
    return "noop"
