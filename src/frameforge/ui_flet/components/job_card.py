"""Queue / history job card and floating selection bar (Flet)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frameforge.ui_flet.job_view import OVERFLOW_IDS, card_view
from frameforge.ui_flet.theme import COLORS, RADIUS_CARD


def _pill(text: str, *, bg: str, fg: str) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        bgcolor=bg,
        border_radius=999,
        content=ft.Text(text, size=11, color=fg, weight=ft.FontWeight.W_500),
    )


def status_colors(status: str) -> tuple[str, str]:
    if status in {"Completed"}:
        return COLORS["success_bg"], COLORS["success"]
    if status in {"Failed", "BLOCKED 4K+"}:
        return COLORS["danger_bg"], COLORS["danger"]
    if status in {"Downloading", "Upscaling", "Converting"}:
        return COLORS["select"], COLORS["accent"]
    if status == "Paused":
        return COLORS["warn_bg"], COLORS["warn"]
    return "#F1F5F9", COLORS["text_secondary"]


def build_job_card(
    job: Any,
    *,
    selected: bool,
    expanded: bool,
    show_progress: bool,
    on_toggle: Callable[[int], None] | None = None,
    on_retry: Callable[[int], None] | None = None,
    on_reauth: Callable[[int], None] | None = None,
    on_expand: Callable[[int], None] | None = None,
    on_overflow: Callable[[int, str], None] | None = None,
) -> ft.Container:
    view = card_view(job, selected=selected, expanded=expanded, show_progress=show_progress)
    bg, fg = status_colors(view["status"])
    fill = COLORS["select"] if selected else COLORS["surface"]
    checks = ft.Checkbox(
        value=selected,
        on_change=lambda _e, jid=job.id: on_toggle(jid) if on_toggle else None,
    )
    thumb = ft.Container(
        width=72,
        height=48,
        bgcolor="#E2E8F0",
        border_radius=8,
        content=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color=COLORS["text_secondary"]),
    )
    title = ft.Text(view["title"], color=COLORS["text_primary"], weight=ft.FontWeight.W_600, size=14)
    meta_bits = [b for b in (view["domain"], view["resolution"]) if b]
    meta = ft.Text(" • ".join(meta_bits) or view["url"], color=COLORS["text_secondary"], size=12)
    badges = [_pill(view["status"], bg=bg, fg=fg)]
    if view["recommended"]:
        badges.append(_pill("Recommended 2x", bg=COLORS["warn_bg"], fg=COLORS["warn"]))
    menu = ft.PopupMenuButton(
        items=[
            ft.PopupMenuItem(content=aid.replace("_", " ").title(), data=aid)
            for aid in OVERFLOW_IDS
        ],
        on_select=lambda e, jid=job.id: on_overflow(jid, str(e.control.data or e.data or ""))
        if on_overflow
        else None,
    )
    progress = None
    if view["progress"] is not None:
        progress = ft.ProgressBar(value=min(1.0, max(0.0, view["progress"] / 100.0)), color=COLORS["progress"], bgcolor="#E2E8F0")
    fail_row = None
    if view["failed"]:
        cause_btn = ft.TextButton(
            content=view["cause"] or "Failed",
            on_click=lambda _e, jid=job.id: on_expand(jid) if on_expand else None,
        )
        actions = None
        if view["expanded"]:
            actions = ft.Row(
                [
                    ft.FilledButton(
                        content="Re-authenticate",
                        bgcolor=COLORS["accent"],
                        on_click=lambda _e, jid=job.id: on_reauth(jid) if on_reauth else None,
                    ),
                    ft.OutlinedButton(
                        content="Retry",
                        on_click=lambda _e, jid=job.id: on_retry(jid) if on_retry else None,
                    ),
                ],
                spacing=8,
            )
        fail_row = ft.Container(
            bgcolor=COLORS["danger_bg"],
            border_radius=8,
            padding=8,
            content=ft.Column([cause_btn] + ([actions] if actions else []), spacing=6),
        )
    body_controls: list[ft.Control] = [
        ft.Row(
            [checks, thumb, ft.Column([title, meta], expand=True, spacing=2), *badges, menu],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )
    ]
    if progress is not None:
        body_controls.append(progress)
    if fail_row is not None:
        body_controls.append(fail_row)
    return ft.Container(
        bgcolor=fill,
        border=ft.Border.all(1, COLORS["accent"] if selected else COLORS["border"]),
        border_radius=RADIUS_CARD,
        padding=12,
        data={"job_id": job.id, "view": view},
        content=ft.Column(body_controls, spacing=8),
        shadow=ft.BoxShadow(blur_radius=8, color="#0F172A14", offset=ft.Offset(0, 1)),
    )


def build_floating_bar(
    spec: dict[str, Any],
    *,
    on_download: Callable[[], None] | None = None,
    on_upscale: Callable[[], None] | None = None,
    on_convert: Callable[[], None] | None = None,
    on_more: Callable[[str], None] | None = None,
) -> ft.Container:
    buttons: list[ft.Control] = [
        ft.Text(f"{spec['count']} selected", color=COLORS["accent"], weight=ft.FontWeight.W_600),
        ft.Container(expand=True),
    ]
    if spec.get("show_download"):
        buttons.append(
            ft.FilledButton(content="Download selected", bgcolor=COLORS["accent"], on_click=lambda _e: on_download and on_download())
        )
    if spec.get("show_upscale"):
        buttons.append(ft.OutlinedButton(content="Upscale 2x", on_click=lambda _e: on_upscale and on_upscale()))
    if spec.get("show_convert"):
        buttons.append(ft.OutlinedButton(content="Convert to MP3", on_click=lambda _e: on_convert and on_convert()))
    buttons.append(
        ft.PopupMenuButton(
            content=ft.OutlinedButton(content="More"),
            items=[
                ft.PopupMenuItem(content="Set format", data="set_format"),
                ft.PopupMenuItem(content="Clear finished", data="clear_finished"),
                ft.PopupMenuItem(content="Select recommended", data="select_recommended"),
                ft.PopupMenuItem(content="Clear selected", data="clear_selected"),
                ft.PopupMenuItem(content="Download all pending", data="download_all"),
            ],
            on_select=lambda e: on_more(str(getattr(e.control, "data", None) or getattr(e, "data", "") or ""))
            if on_more
            else None,
        )
    )
    return ft.Container(
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=16,
        padding=12,
        visible=True,
        shadow=ft.BoxShadow(blur_radius=16, color="#0F172A22", offset=ft.Offset(0, 4)),
        content=ft.Row(buttons, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        data=spec,
    )


def empty_queue_state() -> ft.Container:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.Text("Queue is empty", size=20, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                ft.Text(
                    "Add URLs above or import a file to get started.",
                    color=COLORS["text_secondary"],
                ),
                ft.Text(
                    "Tip: Downloads never start until you press Download",
                    color=COLORS["accent"],
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
    )
