"""Queue / history job card, floating selection bar, and queue chrome row (Flet)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frameforge.ui_flet.elevation import (
    bind_hover_elevation,
    elevated_filled_button,
    elevated_outlined_button,
)
from frameforge.ui_flet.job_view import MORE_LABELS, OVERFLOW_LABELS, overflow_actions
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
    if status == "Failed":
        return COLORS["danger_bg"], COLORS["danger"]
    if status == "BLOCKED 4K+":
        return COLORS["warn_bg"], COLORS["warn"]
    if status in {"Downloading", "Upscaling", "Converting", "Starting"}:
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
    from frameforge.ui_flet.job_view import card_view

    view = card_view(job, selected=selected, expanded=expanded, show_progress=show_progress)
    bg, fg = status_colors(view["status"])
    fill = COLORS["select"] if selected else COLORS["surface"]
    if view["failed"] and not selected:
        fill = COLORS["danger_bg"]
    elif view["blocked_4k"] and not selected:
        fill = COLORS["warn_bg"]
    elif view.get("active") and not selected:
        fill = COLORS["select"]
    border_c = COLORS["danger"] if view["failed"] else (
        COLORS["warn"] if view["blocked_4k"] else (COLORS["accent"] if (selected or view.get("active")) else COLORS["border"])
    )
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
    menu_items = []
    for aid in overflow_actions(job):
        menu_items.append(
            ft.PopupMenuItem(
                content=OVERFLOW_LABELS.get(aid, aid.replace("_", " ").title()),
                on_click=lambda _e=None, jid=job.id, action=aid: on_overflow(jid, action) if on_overflow else None,
            )
        )
    menu = ft.PopupMenuButton(items=menu_items, tooltip="More actions")
    overflow = bind_hover_elevation(
        ft.Container(
            content=menu,
            padding=4,
            border_radius=8,
            data={"kind": "overflow"},
        )
    )
    progress_bar = None
    progress_label = None
    if view["progress"] is not None:
        pct = float(view["progress"])
        progress_bar = ft.ProgressBar(
            value=None if pct <= 0 else min(1.0, max(0.0, pct / 100.0)),
            color=COLORS["progress"],
            bgcolor="#E2E8F0",
        )
        bits = [f"{int(pct)}%"] if pct > 0 else ["Starting…"]
        if view.get("speed"):
            bits.append(str(view["speed"]))
        if view.get("eta"):
            bits.append(str(view["eta"]))
        progress_label = ft.Text("  ".join(bits), size=11, color=COLORS["text_secondary"])
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
                    elevated_filled_button(
                        "Re-authenticate",
                        on_click=lambda _e, jid=job.id: on_reauth(jid) if on_reauth else None,
                    ),
                    elevated_outlined_button(
                        "Retry",
                        on_click=lambda _e, jid=job.id: on_retry(jid) if on_retry else None,
                    ),
                ],
                spacing=8,
            )
        fail_row = ft.Container(
            bgcolor=COLORS["danger_bg"],
            border=ft.Border.all(1, COLORS["danger"]),
            border_radius=8,
            padding=8,
            content=ft.Column([cause_btn] + ([actions] if actions else []), spacing=6),
        )
    body_controls: list[ft.Control] = [
        ft.Row(
            [checks, thumb, ft.Column([title, meta], expand=True, spacing=2), *badges, overflow],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )
    ]
    if progress_bar is not None:
        body_controls.append(progress_bar)
        if progress_label is not None:
            body_controls.append(progress_label)
    if fail_row is not None:
        body_controls.append(fail_row)
    card = ft.Container(
        bgcolor=fill,
        border=ft.Border.all(1, border_c),
        border_radius=RADIUS_CARD,
        padding=12,
        data={
            "job_id": job.id,
            "view": view,
            "progress_bar": progress_bar,
            "progress_label": progress_label,
            "failed": view["failed"],
        },
        content=ft.Column(body_controls, spacing=8),
    )
    return bind_hover_elevation(card, selected=selected)


def _more_menu(spec: dict[str, Any], on_more: Callable[[str], None] | None) -> ft.PopupMenuButton:
    """Plain PopupMenuButton — never nest another Button (that swallows clicks)."""
    items = []
    for aid in spec.get("more_items") or [
        "set_format",
        "clear_finished",
        "select_recommended",
        "clear_selected",
        "download_all",
    ]:
        items.append(
            ft.PopupMenuItem(
                content=MORE_LABELS.get(aid, aid.replace("_", " ").title()),
                on_click=lambda _e=None, action=aid: on_more(action) if on_more else None,
            )
        )
    return ft.PopupMenuButton(
        content=ft.Text("More", color=COLORS["accent"], weight=ft.FontWeight.W_600),
        tooltip="More",
        items=items,
        data={"kind": "more", "items": [it.content for it in items]},
    )


def build_floating_bar(
    spec: dict[str, Any],
    *,
    on_download: Callable[[], None] | None = None,
    on_upscale: Callable[[], None] | None = None,
    on_convert: Callable[[], None] | None = None,
    on_clear: Callable[[], None] | None = None,
    on_retry: Callable[[], None] | None = None,
    on_more: Callable[[str], None] | None = None,
) -> ft.Container:
    buttons: list[ft.Control] = [
        ft.Text(f"{spec['count']} selected", color=COLORS["accent"], weight=ft.FontWeight.W_600),
        ft.Container(expand=True),
    ]
    if spec.get("show_download"):
        buttons.append(
            elevated_filled_button("Download selected", on_click=lambda _e: on_download and on_download())
        )
    if spec.get("show_upscale"):
        buttons.append(elevated_outlined_button("Upscale 2x", on_click=lambda _e: on_upscale and on_upscale()))
    if spec.get("show_convert"):
        buttons.append(elevated_outlined_button("Convert to MP3", on_click=lambda _e: on_convert and on_convert()))
    if spec.get("show_retry"):
        buttons.append(elevated_outlined_button("Retry selected", on_click=lambda _e: on_retry and on_retry()))
    if spec.get("show_clear"):
        buttons.append(elevated_outlined_button("Clear selected", on_click=lambda _e: on_clear and on_clear()))
    buttons.append(_more_menu(spec, on_more))
    bar = ft.Container(
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=16,
        padding=12,
        visible=True,
        content=ft.Row(buttons, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        data=spec,
    )
    return bind_hover_elevation(bar)


def build_queue_chrome(
    spec: dict[str, Any],
    *,
    on_download_all: Callable[[], None] | None = None,
    on_retry_failed: Callable[[], None] | None = None,
    on_clear_finished: Callable[[], None] | None = None,
    on_clear_selected: Callable[[], None] | None = None,
    on_undo: Callable[[], None] | None = None,
    on_pause: Callable[[], None] | None = None,
    on_stop: Callable[[], None] | None = None,
) -> ft.Container:
    if not spec.get("visible"):
        return ft.Container(visible=False, data=spec)
    buttons: list[ft.Control] = []
    if spec.get("show_pause"):
        buttons.append(
            elevated_outlined_button("Pause", on_click=lambda _e: on_pause and on_pause())
        )
    if spec.get("show_stop"):
        buttons.append(
            elevated_outlined_button("Stop", on_click=lambda _e: on_stop and on_stop())
        )
    if spec.get("show_download_all"):
        buttons.append(
            elevated_filled_button(
                "Download all pending",
                on_click=lambda _e: on_download_all and on_download_all(),
            )
        )
    if spec.get("show_retry_failed"):
        buttons.append(
            elevated_outlined_button("Retry failed", on_click=lambda _e: on_retry_failed and on_retry_failed())
        )
    if spec.get("show_clear_finished"):
        buttons.append(
            elevated_outlined_button("Clear finished", on_click=lambda _e: on_clear_finished and on_clear_finished())
        )
    buttons.append(
        elevated_outlined_button(
            "Clear selected",
            disabled=not spec.get("clear_selected_enabled"),
            on_click=lambda _e: on_clear_selected and on_clear_selected(),
        )
    )
    if spec.get("show_undo"):
        buttons.append(elevated_filled_button("Undo", on_click=lambda _e: on_undo and on_undo()))
    row = ft.Container(
        visible=True,
        data=spec,
        content=ft.Row(buttons, spacing=8, wrap=True),
        padding=4,
        border_radius=10,
    )
    return bind_hover_elevation(row)


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
