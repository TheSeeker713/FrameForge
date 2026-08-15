"""Shell safety: never GetForegroundWindow / DWM on foreign HWNDs."""

from __future__ import annotations

from pathlib import Path

from tests.flet_fakes import FakePage
from frameforge.ui_flet.window_chrome import (
    apply_page_chrome,
    disable_dwm_glass,
    frameforge_native_hwnd,
)

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "frameforge"
_FORBIDDEN = (
    "GetForegroundWindow",
    "SetThemeAppProperties",
    "ThemeActive",
    "ThemeManager",
    "SystemParametersInfo",
)


def test_window_chrome_source_has_no_foreground_hwnd():
    text = (_SRC / "ui_flet" / "window_chrome.py").read_text(encoding="utf-8")
    assert "GetForegroundWindow" not in text
    assert "DwmSetWindowAttribute" not in text
    assert "windll.user32" not in text
    assert "windll.dwmapi" not in text


def test_production_ui_has_no_forbidden_shell_apis():
    hits: list[str] = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN:
            if needle in text:
                hits.append(f"{path.relative_to(_ROOT)}: {needle}")
    assert hits == []


def test_disable_dwm_glass_is_noop_without_our_hwnd():
    page = FakePage()
    assert frameforge_native_hwnd(page) is None
    assert disable_dwm_glass(page) == "noop"
    assert disable_dwm_glass(None) == "noop"
    apply_page_chrome(page, set_size=False)
    assert page.window.bgcolor is not None
    assert page.window.title_bar_hidden is False


def test_reveal_uses_explorer_select_not_kill():
    from frameforge.util.reveal import explorer_select_command

    cmd = explorer_select_command(Path("C:/tmp/file.mp4"))
    assert cmd[0] == "explorer"
    assert cmd[1].startswith("/select,")
    assert "taskkill" not in " ".join(cmd).lower()
    assert "/restart" not in " ".join(cmd).lower()
