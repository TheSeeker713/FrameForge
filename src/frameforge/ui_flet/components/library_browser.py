"""Book and folder browser for the Library tab.

Visible with zero videos. Adding a video files it into a book; the file stays put.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frameforge.library.books import BOOKS, CATALOG
from frameforge.ui_flet.theme import COLORS, FONT_FAMILY


def fill_library_browser(
    host: ft.Column,
    *,
    book: str,
    folder: str | None,
    folders: list[tuple[str, int]],
    clips: list[tuple[Any, str]],
    on_book: Callable[[str], None],
    on_folder: Callable[[str | None], None],
    on_add: Callable[..., None],
) -> None:
    book_row = ft.Row(
        [_chip(name, name == book, lambda e, name=name: on_book(name)) for name in BOOKS],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )
    folder_row = ft.Row(
        [
            _chip("All", folder is None, lambda e: on_folder(None)),
            *[
                _chip(f"{name} ({count})" if count else name, folder == name, lambda e, name=name: on_folder(name))
                for name, count in folders
            ],
        ],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )
    if clips:
        body: ft.Control = ft.Column(
            [_clip_row(item, folder_name) for item, folder_name in clips],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    else:
        where = folder or book
        body = ft.Container(
            expand=True,
            bgcolor=COLORS["surface"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=16,
            padding=28,
            content=ft.Column(
                [
                    ft.Text(book, size=22, weight=ft.FontWeight.W_600, color=COLORS["text_primary"], font_family=FONT_FAMILY),
                    ft.Text(
                        f"{where} is empty. Add videos from any folder. FrameForge files them into a book and leaves the files where they are.",
                        size=14,
                        color=COLORS["text_secondary"],
                        font_family=FONT_FAMILY,
                    ),
                    ft.FilledButton(
                        content="Add videos",
                        on_click=on_add,
                        bgcolor=COLORS["accent"],
                        color="#FFFFFF",
                    ),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
    host.controls = [
        ft.Text("Library", size=20, weight=ft.FontWeight.W_600, color=COLORS["text_primary"], font_family=FONT_FAMILY),
        book_row,
        folder_row,
        body,
    ]
    host.data = {
        "kind": "library_books",
        "book": book,
        "folder": folder,
        "books": list(BOOKS),
        "folders": [name for name, _count in folders],
        "clips": [getattr(item, "title", None) for item, _folder in clips],
        "catalog": {name: list(CATALOG[name]) for name in BOOKS},
    }


def _chip(label: str, selected: bool, on_click: Callable[..., None]) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            label,
            size=13,
            color=COLORS["accent"] if selected else COLORS["text_primary"],
            font_family=FONT_FAMILY,
        ),
        bgcolor=COLORS["select"] if selected else COLORS["surface"],
        border=ft.Border.all(1, COLORS["accent"] if selected else COLORS["border"]),
        border_radius=999,
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        on_click=on_click,
    )


def _clip_row(item: Any, folder_name: str) -> ft.Container:
    title = item.title or "Untitled"
    return ft.Container(
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=12,
        padding=12,
        content=ft.Row(
            [
                ft.Container(
                    width=72,
                    height=40,
                    bgcolor=COLORS["select"],
                    border_radius=8,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(title[:1].upper(), color=COLORS["accent"], weight=ft.FontWeight.W_600),
                ),
                ft.Column(
                    [
                        ft.Text(title, size=14, color=COLORS["text_primary"], font_family=FONT_FAMILY),
                        ft.Text(folder_name, size=12, color=COLORS["text_secondary"], font_family=FONT_FAMILY),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=12,
        ),
    )
