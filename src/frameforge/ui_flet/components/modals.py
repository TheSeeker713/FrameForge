"""Flet dialogs: format, authenticate, bulk import, playlist, quit-while-busy."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.download.formats import PRESET_LABELS
from frameforge.gui.exit_policy import CHOICE_QUIT_IDLE, CHOICE_STAY
from frameforge.ui_flet.theme import COLORS


def close_icon_button(on_close: Any) -> ft.IconButton:
    return ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=COLORS["danger"],
        tooltip="Close",
        on_click=on_close,
    )


def wire_closable(dlg: ft.AlertDialog, on_close: Any) -> ft.AlertDialog:
    """Click-outside, X, Escape (via page), and on_dismiss all reach on_close.

    ``modal=False`` lets a barrier click dismiss. Duplicate Close icons are skipped.
    """
    dlg.modal = False
    dlg.on_dismiss = on_close
    actions = list(dlg.actions or [])
    already = any(
        isinstance(a, ft.IconButton) and getattr(a, "tooltip", None) == "Close" for a in actions
    )
    if not already:
        dlg.actions = [close_icon_button(on_close), *actions]
    return dlg


def format_dialog(*, on_apply: Any, on_cancel: Any) -> ft.AlertDialog:
    radios = [ft.Radio(value=label, label=label) for label in PRESET_LABELS]
    rg = ft.RadioGroup(content=ft.Column(radios), value="Best")

    def apply(_e=None):
        on_apply(rg.value or "Best")

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Set format"),
        content=rg,
        actions=[
            ft.OutlinedButton(content="Cancel", on_click=on_cancel),
            ft.FilledButton(content="Apply", bgcolor=COLORS["accent"], on_click=apply),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=on_cancel,
    )
    dlg.data = {"apply": apply, "cancel": on_cancel, "group": rg}
    return dlg


def authenticate_dialog(
    domain: str,
    *,
    on_chrome: Any,
    on_edge: Any,
    on_firefox: Any,
    on_txt: Any,
    on_close: Any,
    on_copy: Any | None = None,
    on_open_cookies: Any | None = None,
    prefill: str = "",
    error: str = "",
) -> ft.AlertDialog:
    field = ft.TextField(
        value=prefill or domain or "",
        hint_text="https://example.com/ or example.com",
        border_color=COLORS["border"],
        focused_border_color=COLORS["accent"],
    )
    err = ft.Text(error, color=COLORS["danger"], visible=bool(error))
    from frameforge.download.cookies import cookie_store_status

    store = cookie_store_status()
    cookies_path = ft.Text(
        f"Cookies folder: {store['directory']}",
        color=COLORS["text_secondary"],
        size=12,
        selectable=True,
    )
    cookies_list = ft.Text(
        f"Domain files: {store['label']}",
        color=COLORS["text_secondary"],
        size=12,
        selectable=True,
    )

    def _open_cookies(_e=None) -> None:
        if on_open_cookies:
            on_open_cookies()

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Authenticate site"),
        content=ft.Column(
            [
                ft.Text(f"Authenticate {domain}", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Prefer Firefox import, or a Netscape cookies.txt from an extension. "
                    "Chrome often fails on modern Windows (App-Bound Encryption / DPAPI) — "
                    "FrameForge cannot decrypt those cookies. Log in in Firefox first if the site shows a bot check.",
                    color=COLORS["text_secondary"],
                ),
                cookies_path,
                cookies_list,
                ft.OutlinedButton(content="Open cookies folder", on_click=_open_cookies),
                field,
                ft.ListTile(title=ft.Text("Import from Firefox (recommended)"), on_click=on_firefox),
                ft.ListTile(title=ft.Text("Choose cookies.txt file"), on_click=on_txt),
                ft.Text(
                    "Export steps: open the site in Firefox → log in → use a cookies.txt extension "
                    "(e.g. “Get cookies.txt LOCALLY”) → save the file → Choose cookies.txt file here.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                ft.ListTile(title=ft.Text("Import from Edge"), on_click=on_edge),
                ft.ListTile(
                    title=ft.Text("Import from Chrome (often blocked by App-Bound Encryption)"),
                    on_click=on_chrome,
                ),
                err,
            ],
            width=420,
            spacing=8,
        ),
        actions=[
            ft.OutlinedButton(content="Copy error", on_click=on_copy),
            ft.OutlinedButton(content="Cancel", on_click=on_close),
            ft.FilledButton(content="Done", bgcolor=COLORS["accent"], on_click=on_close),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=on_close,
    )
    dlg.data = {
        "field": field,
        "error": err,
        "on_chrome": on_chrome,
        "on_edge": on_edge,
        "on_firefox": on_firefox,
        "on_txt": on_txt,
        "on_close": on_close,
        "on_copy": on_copy,
        "on_open_cookies": on_open_cookies,
        "cookies_path": cookies_path,
        "cookies_list": cookies_list,
        "cookies_dir": store["directory"],
        "cookie_files": store["label"],
    }
    return dlg


def bulk_import_dialog(new_count: int, dup_count: int, *, on_add: Any, on_cancel: Any) -> ft.AlertDialog:
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Bulk import"),
        content=ft.Column(
            [
                ft.Text(f"New URLs: {new_count}", color=COLORS["accent"], size=22, weight=ft.FontWeight.BOLD),
                ft.Text(f"Duplicates skipped: {dup_count}", color=COLORS["text_secondary"]),
                ft.Text("Add to queue only — downloads will not start until you press Download."),
            ],
            width=400,
            spacing=8,
        ),
        actions=[
            ft.FilledButton(content="Add to queue", bgcolor=COLORS["accent"], on_click=on_add),
            ft.OutlinedButton(content="Cancel", on_click=on_cancel),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=on_cancel,
    )
    dlg.data = {"on_add": on_add, "on_cancel": on_cancel}
    return dlg


def playlist_dialog(
    title: str,
    entries: list[Any],
    *,
    on_enqueue: Any,
    on_cancel: Any,
    on_select_all: Any | None = None,
    on_select_none: Any | None = None,
) -> ft.AlertDialog:
    n = len(entries)
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Playlist"),
        content=ft.Column(
            [
                ft.Text(f"{title} • {n} videos found", color=COLORS["text_secondary"]),
                ft.TextButton(content="Select all", on_click=lambda e: on_select_all and on_select_all()),
                ft.TextButton(content="Select none", on_click=lambda e: on_select_none and on_select_none()),
            ],
            width=440,
        ),
        actions=[
            ft.FilledButton(content=f"Enqueue selected ({n})", bgcolor=COLORS["accent"], on_click=on_enqueue),
            ft.OutlinedButton(content="Cancel", on_click=on_cancel),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=on_cancel,
    )
    dlg.data = {"on_enqueue": on_enqueue, "on_cancel": on_cancel}
    return dlg


def quit_confirm_dialog(*, on_quit: Any, on_cancel: Any, busy: bool = False) -> ft.AlertDialog:
    """Single confirm: Quit or Cancel. No Force-quit / pause / wait stack."""
    body = (
        "A download is in progress. Quit anyway?"
        if busy
        else "Quit FrameForge?"
    )
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Quit FrameForge?"),
        content=ft.Text(body, color=COLORS["text_secondary"]),
        actions=[
            ft.OutlinedButton(content="Cancel", on_click=lambda _e: on_cancel()),
            ft.FilledButton(content="Quit", bgcolor=COLORS["danger"], on_click=lambda _e: on_quit()),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=lambda _e=None: on_cancel(),
    )
    dlg.data = {"on_quit": on_quit, "on_cancel": on_cancel, "busy": busy}
    return dlg


def quit_busy_dialog(*, on_choice: Any, on_cancel: Any, busy: bool = True) -> ft.AlertDialog:
    """Back-compat wrapper: maps to Quit / Cancel only."""
    def _quit(_e=None) -> None:
        on_choice(CHOICE_QUIT_IDLE)

    def _stay(_e=None) -> None:
        on_choice(CHOICE_STAY)

    dlg = quit_confirm_dialog(on_quit=_quit, on_cancel=_stay, busy=busy)
    dlg.data["on_choice"] = on_choice
    dlg.data["force"] = CHOICE_QUIT_IDLE
    return dlg
