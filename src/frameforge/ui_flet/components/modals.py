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


def format_dialog(*, on_apply: Any, on_cancel: Any) -> ft.AlertDialog:
    group: dict[str, str] = {"value": "Best"}
    radios = []
    for label in PRESET_LABELS:
        radios.append(
            ft.Radio(value=label, label=label)
        )
    rg = ft.RadioGroup(content=ft.Column(radios), value="Best")

    def apply(_e=None):
        on_apply(rg.value or "Best")

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Set format"),
        content=rg,
        actions=[
            ft.OutlinedButton(content="Cancel", on_click=on_cancel),
            ft.FilledButton(content="Apply", bgcolor=COLORS["accent"], on_click=apply),
        ],
        bgcolor=COLORS["surface"],
    )


def authenticate_dialog(domain: str, *, on_firefox: Any, on_txt: Any, on_close: Any) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Authenticate site"),
        content=ft.Column(
            [
                ft.Text(f"Authenticate {domain}", weight=ft.FontWeight.BOLD),
                ft.Text("Import cookies from Firefox or provide a cookies.txt file.", color=COLORS["text_secondary"]),
                ft.ListTile(title=ft.Text("Import from Firefox"), on_click=on_firefox),
                ft.ListTile(title=ft.Text("Choose cookies.txt file"), on_click=on_txt),
            ],
            width=420,
            spacing=8,
        ),
        actions=[
            ft.OutlinedButton(content="Cancel", on_click=on_close),
            ft.FilledButton(content="Done", bgcolor=COLORS["accent"], on_click=on_close),
        ],
        bgcolor=COLORS["surface"],
    )


def bulk_import_dialog(new_count: int, dup_count: int, *, on_add: Any, on_cancel: Any) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
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
    )


def playlist_dialog(title: str, entries: list[Any], *, on_enqueue: Any, on_cancel: Any) -> ft.AlertDialog:
    n = len(entries)
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Playlist"),
        content=ft.Column(
            [
                ft.Text(f"{title} • {n} videos found", color=COLORS["text_secondary"]),
                ft.TextButton(content="Select all"),
                ft.TextButton(content="Select none"),
            ],
            width=440,
        ),
        actions=[
            ft.FilledButton(content=f"Enqueue selected ({n})", bgcolor=COLORS["accent"], on_click=on_enqueue),
            ft.OutlinedButton(content="Cancel", on_click=on_cancel),
        ],
        bgcolor=COLORS["surface"],
    )


def quit_busy_dialog(*, on_choice: Any, on_cancel: Any) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
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
    )
