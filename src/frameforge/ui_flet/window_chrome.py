"""Force an opaque native HWND. v0.5.2 one-shot bgcolor failed the field drag test."""

from __future__ import annotations

import sys
from typing import Any

import flet as ft

from frameforge import __version__
from frameforge.ui_flet.theme import COLORS, FONT_FAMILY, WINDOW_HEIGHT, WINDOW_WIDTH

# 6-digit hex only — never None, never 8-digit alpha, never "transparent".
OPAQUE_BG = COLORS["app_bg"]


def chrome_snapshot(page: Any) -> dict[str, Any]:
    """Runtime flags the user/agent can log when drag still fails."""
    win = getattr(page, "window", None)
    return {
        "page_bgcolor": getattr(page, "bgcolor", None),
        "window_bgcolor": getattr(win, "bgcolor", None) if win is not None else None,
        "opacity": getattr(win, "opacity", None) if win is not None else None,
        "shadow": getattr(win, "shadow", None) if win is not None else None,
        "title_bar_hidden": getattr(win, "title_bar_hidden", None) if win is not None else None,
        "frameless": getattr(win, "frameless", None) if win is not None else None,
        "visible": getattr(win, "visible", None) if win is not None else None,
        "ignore_mouse_events": getattr(win, "ignore_mouse_events", None) if win is not None else None,
        "transparent": getattr(win, "transparent", None) if win is not None else None,
    }


def apply_page_chrome(page: ft.Page, *, set_size: bool = True) -> dict[str, Any]:
    """Solid page + window fill, native title bar, no OS shadow, no glass.

    ``set_size`` only on first attach — reapplying width/height during drag fights the user.
    """
    page.title = f"FrameForge {__version__}"
    page.bgcolor = OPAQUE_BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
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
        window.title_bar_hidden = False
        window.frameless = False
        if hasattr(window, "transparent"):
            window.transparent = False
        if getattr(window, "ignore_mouse_events", False):
            window.ignore_mouse_events = False
        disable_dwm_glass()
    return chrome_snapshot(page)


def disable_dwm_glass() -> None:
    """Ask DWM not to use Mica/acrylic on the foreground FrameForge window (Windows 11)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return
        dwmapi = ctypes.windll.dwmapi
        # DWMWA_TRANSITIONS_FORCEDISABLED = 3
        val = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 3, ctypes.byref(val), ctypes.sizeof(val))
        # DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_NONE = 1
        none = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(none), ctypes.sizeof(none))
        # DWMWA_NCRENDERING_POLICY = 2, DWMNCRP_DISABLED = 1 (no glass frame)
        policy = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 2, ctypes.byref(policy), ctypes.sizeof(policy))
    except Exception:  # noqa: BLE001
        return
