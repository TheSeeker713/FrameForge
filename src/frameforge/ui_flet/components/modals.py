"""Flet dialogs: format, authenticate, bulk import, playlist, quit-while-busy."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.download.formats import PRESET_LABELS
from frameforge.gui.exit_policy import (
    CHOICE_CANCEL_AND_QUIT,
    CHOICE_PAUSE_AND_QUIT,
    CHOICE_WAIT_THEN_QUIT,
)
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
    on_firefox: Any,
    on_txt: Any,
    on_close: Any,
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
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Authenticate site"),
        content=ft.Column(
            [
                ft.Text(f"Authenticate {domain}", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Import cookies from Firefox or provide a cookies.txt file.",
                    color=COLORS["text_secondary"],
                ),
                field,
                ft.ListTile(title=ft.Text("Import from Firefox"), on_click=on_firefox),
                ft.ListTile(title=ft.Text("Choose cookies.txt file"), on_click=on_txt),
                err,
            ],
            width=420,
            spacing=8,
        ),
        actions=[
            ft.OutlinedButton(content="Cancel", on_click=on_close),
            ft.FilledButton(content="Done", bgcolor=COLORS["accent"], on_click=on_close),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=on_close,
    )
    dlg.data = {
        "field": field,
        "error": err,
        "on_firefox": on_firefox,
        "on_txt": on_txt,
        "on_close": on_close,
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


def quit_busy_dialog(*, on_choice: Any, on_cancel: Any) -> ft.AlertDialog:
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Download in progress"),
        content=ft.Column(
            [
                ft.ListTile(
                    title=ft.Text("Cancel download and quit"),
                    on_click=lambda _e: on_choice(CHOICE_CANCEL_AND_QUIT),
                ),
                ft.ListTile(
                    title=ft.Text("Pause download and quit"),
                    on_click=lambda _e: on_choice(CHOICE_PAUSE_AND_QUIT),
                ),
                ft.ListTile(
                    title=ft.Text("Wait until finished then quit"),
                    on_click=lambda _e: on_choice(CHOICE_WAIT_THEN_QUIT),
                ),
            ],
            width=460,
        ),
        actions=[ft.OutlinedButton(content="Cancel", on_click=on_cancel)],
        bgcolor=COLORS["surface"],
        on_dismiss=on_cancel,
    )
    dlg.data = {"on_choice": on_choice, "on_cancel": on_cancel}
    return dlg
