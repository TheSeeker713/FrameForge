"""Right-hand details for the selected library card."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frameforge.library.versions import http_url
from frameforge.ui_flet.theme import COLORS, FONT_FAMILY

_ROLE_ORDER = {"original": 0, "upscaled": 1, "linked": 2}


def build_library_detail(
    item: Any,
    files: list[Any],
    *,
    on_play: Callable[[int], None],
    on_play_file: Callable[[str], None],
    on_reveal: Callable[[str], None],
    on_open_source: Callable[[str], None],
    on_copy: Callable[[str], None],
    on_rename: Callable[[str], None],
) -> ft.Container:
    ordered = sorted(files, key=lambda row: (_ROLE_ORDER.get(row.role, 9), row.scale or 0, row.id))
    source = http_url(getattr(item, "source_url", None))
    rows: list[ft.Control] = [
        ft.Text(item.title or "Untitled", size=18, weight=ft.FontWeight.W_600, color=COLORS["text_primary"], font_family=FONT_FAMILY),
        ft.TextField(
            value=item.title or "",
            label="Title",
            on_submit=lambda e: on_rename(e.control.value or ""),
        ),
        ft.FilledButton(content="Play", on_click=lambda _e: on_play(item.id)),
    ]
    if source:
        rows.append(ft.Text(source, size=12, selectable=True, color=COLORS["accent"], font_family=FONT_FAMILY))
        rows.append(
            ft.Row(
                [
                    ft.TextButton(content="Open source page", on_click=lambda _e: on_open_source(source)),
                    ft.TextButton(content="Copy URL", on_click=lambda _e: on_copy(source)),
                ]
            )
        )
    version_paths: list[str] = []
    for row in ordered:
        version_paths.append(row.path)
        label = row.role
        if row.scale:
            label = f"Upscaled {row.scale}x"
        elif row.role == "original":
            label = "Original"
        elif row.role == "linked":
            label = "Linked"
        extra = row.model or ""
        rows.append(
            ft.Column(
                [
                    ft.Text(f"{label} {extra}".strip(), size=13, color=COLORS["text_primary"], font_family=FONT_FAMILY),
                    ft.Text(row.path, size=11, color=COLORS["text_secondary"], max_lines=2, tooltip=row.path),
                    ft.Row(
                        [
                            ft.TextButton(content="Play this version", on_click=lambda _e, path=row.path: on_play_file(path)),
                            ft.TextButton(content="Reveal", on_click=lambda _e, path=row.path: on_reveal(path)),
                            ft.TextButton(content="Copy path", on_click=lambda _e, path=row.path: on_copy(path)),
                        ],
                        wrap=True,
                    ),
                ],
                spacing=2,
            )
        )
    if item.job_id:
        rows.append(ft.Text(f"Job {item.job_id}", size=12, color=COLORS["text_secondary"], font_family=FONT_FAMILY))
    return ft.Container(
        width=360,
        padding=12,
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=12,
        content=ft.Column(rows, spacing=8, scroll=ft.ScrollMode.AUTO),
        data={
            "kind": "library_detail",
            "item_id": item.id,
            "source_url": source,
            "paths": version_paths,
            "job_id": item.job_id,
        },
    )
