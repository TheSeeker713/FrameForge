"""Left sidebar filters. Books stay a database, not a folder move."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frameforge.library.books import BOOKS, CATALOG
from frameforge.ui_flet.theme import COLORS, FONT_FAMILY


def fill_library_sidebar(
    host: ft.Column,
    *,
    counts: dict[str, Any],
    book: str | None,
    folder: str | None,
    flag: str | None,
    on_all: Callable[[], None],
    on_flag: Callable[[str], None],
    on_book: Callable[[str], None],
    on_folder: Callable[[str], None],
) -> None:
    book_rows = {name: 0 for name in BOOKS}
    folder_rows: dict[str, list[tuple[str, int]]] = {name: [] for name in BOOKS}
    for kind, name, count in counts.get("books", []):
        if kind == "book" and name in book_rows:
            book_rows[name] = count
        elif str(kind).startswith("book:"):
            owner = str(kind).split(":", 1)[1]
            folder_rows.setdefault(owner, []).append((name, count))
    controls: list[ft.Control] = [
        _entry("All videos", counts.get("all", 0), selected=book is None and not flag, on_click=lambda _e: on_all()),
        _entry("Favorites", counts.get("favorites", 0), selected=flag == "favorites", on_click=lambda _e: on_flag("favorites")),
        _entry("Watch later", counts.get("watch_later", 0), selected=flag == "watch_later", on_click=lambda _e: on_flag("watch_later")),
        ft.Text("Books", size=12, color=COLORS["text_secondary"], font_family=FONT_FAMILY),
    ]
    active_folders: list[str] = []
    for name in BOOKS:
        controls.append(
            _entry(name, book_rows.get(name, 0), selected=book == name and folder is None, on_click=lambda _e, name=name: on_book(name))
        )
        if book == name:
            names = [folder_name for folder_name, _count in folder_rows.get(name, [])]
            if not names:
                names = list(CATALOG.get(name, ()))
            active_folders = names
            for folder_name in names:
                count = dict(folder_rows.get(name, [])).get(folder_name, 0)
                controls.append(
                    _entry(
                        f"  {folder_name}",
                        count,
                        selected=folder == folder_name,
                        on_click=lambda _e, folder_name=folder_name: on_folder(folder_name),
                    )
                )
    host.controls = controls
    host.data = {
        "kind": "library_books",
        "book": book,
        "folder": folder,
        "books": list(BOOKS),
        "folders": active_folders or list(CATALOG.get(book or "Movies", ())),
        "clips": [],
        "catalog": {name: list(CATALOG[name]) for name in BOOKS},
        "counts": counts,
    }


def _entry(label: str, count: int, *, selected: bool, on_click: Callable[..., None]) -> ft.Container:
    return ft.Container(
        bgcolor=COLORS["select"] if selected else None,
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        on_click=on_click,
        content=ft.Row(
            [
                ft.Text(label, size=13, expand=True, color=COLORS["text_primary"], font_family=FONT_FAMILY),
                ft.Text(str(count), size=12, color=COLORS["text_secondary"], font_family=FONT_FAMILY),
            ]
        ),
    )
