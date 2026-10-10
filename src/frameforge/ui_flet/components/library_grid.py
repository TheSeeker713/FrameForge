"""Thumbnail card for the library grid."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frameforge.ui_flet.theme import COLORS, FONT_FAMILY


def library_card(
    item: Any,
    *,
    selected: bool = False,
    on_open: Callable[[int], None],
    on_play: Callable[[int], None],
) -> ft.Control:
    title = item.title or "Untitled"
    thumb = item.thumb_path if item.thumb_path else None
    picture = ft.Image(
        src=thumb or "",
        fit=ft.BoxFit.COVER,
        expand=True,
        cache_width=480,
        gapless_playback=True,
        error_content=ft.Icon(ft.Icons.MOVIE_OUTLINED, color=COLORS["text_secondary"], size=28),
        visible=bool(thumb),
    )
    height = item.height
    meta = item.source_site or item.source or ""
    if height:
        meta = f"{meta}  {height}p".strip()
    card = ft.Container(
        bgcolor=COLORS["select"] if selected else COLORS["surface"],
        border=ft.Border.all(1, COLORS["accent"] if selected else COLORS["border"]),
        border_radius=12,
        padding=8,
        data={"item_id": item.id, "path": item.path, "title": title},
        content=ft.Column(
            [
                ft.Container(
                    height=140,
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    bgcolor=COLORS["select"],
                    content=ft.Stack(
                        [
                            picture,
                            ft.Container(
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color="#FFFFFF", size=36),
                            ),
                        ]
                    ),
                ),
                ft.Text(
                    title,
                    size=13,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    color=COLORS["text_primary"],
                    font_family=FONT_FAMILY,
                ),
                ft.Text(meta, size=11, color=COLORS["text_secondary"], font_family=FONT_FAMILY),
            ],
            spacing=6,
        ),
    )
    return ft.GestureDetector(
        content=ft.ContextMenu(
            content=card,
            secondary_items=[
                ft.PopupMenuItem(content="Play", on_click=lambda _e, i=item.id: on_play(i)),
                ft.PopupMenuItem(content="Open details", on_click=lambda _e, i=item.id: on_open(i)),
            ],
        ),
        on_tap=lambda _e, i=item.id: on_open(i),
        on_double_tap=lambda _e, i=item.id: on_play(i),
    )
