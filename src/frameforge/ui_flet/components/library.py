"""Library tab: onboarding, grid, collections, local-only copy."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.library.actions import can_upscale_library_item
from frameforge.library.models import LibraryItem
from frameforge.library.taxonomy import SOURCES, SYSTEM_FLAGS
from frameforge.ui_flet.elevation import elevated_filled_button, elevated_outlined_button
from frameforge.ui_flet.theme import COLORS, RADIUS_CARD


def _date_label(raw: str | None) -> str:
    if not raw:
        return ""
    return str(raw).split("T", 1)[0]


def empty_library_state(
    *,
    onboarded: bool,
    on_setup: Any | None = None,
    on_import: Any | None = None,
    on_scan: Any | None = None,
    pending_count: int = 0,
    orphan_count: int = 0,
) -> ft.Container:
    if onboarded and orphan_count:
        title = "Library folder has unindexed videos"
        body = (
            f"{orphan_count} video file(s) are on disk under your Library folder but not in the index. "
            "Scan to show them here."
        )
        cta = "Scan library folder"
        click = on_scan or on_import
    elif onboarded:
        title = "No clips in Library yet"
        body = (
            "Completed downloads can be imported here. Queue playback still works from the Queue tab."
        )
        cta = "Import completed downloads"
        click = on_import or on_setup
    else:
        title = "Set up your Library"
        body = (
            "Library is a local folder plus SQLite metadata on this PC. "
            "No cloud, no accounts, no sync."
        )
        cta = "Continue setup" if pending_count or on_setup else "Choose Library folder"
        click = on_setup
    btn = elevated_filled_button(cta, on_click=lambda _e: click and click())
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                ft.Text(body, color=COLORS["text_secondary"], size=13, text_align=ft.TextAlign.CENTER),
                btn,
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            width=420,
        ),
        data={"kind": "library_empty", "cta": cta, "orphan_count": orphan_count},
    )


def _thumb_src(raw: str | None) -> str | None:
    if not raw:
        return None
    from pathlib import Path

    path = Path(raw)
    if path.is_file():
        return str(path)
    return None


def library_tile(
    item: LibraryItem,
    *,
    selected: bool = False,
    on_play: Any | None = None,
    on_reveal: Any | None = None,
    on_upscale: Any | None = None,
    on_toggle: Any | None = None,
    on_favorite: Any | None = None,
    on_watch_later: Any | None = None,
) -> ft.Container:
    thumb = _thumb_src(item.thumb_path)
    preview_inner: ft.Control
    if thumb:
        preview_inner = ft.Image(src=thumb, width=200, height=112, fit=ft.BoxFit.COVER)
    else:
        preview_inner = ft.Container(
            width=200,
            height=112,
            bgcolor=COLORS["select"],
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(ft.Icons.MOVIE_OUTLINED, color=COLORS["text_secondary"]),
        )
    preview = ft.Container(
        content=preview_inner,
        width=200,
        height=112,
        on_click=lambda _e, i=item.id: on_play and on_play(i),
        data={"play": item.id},
    )
    upscale_ok = can_upscale_library_item(item)
    upscale_btn = ft.TextButton(
        content="Upscale",
        on_click=lambda _e, i=item.id: on_upscale and on_upscale(i),
        disabled=not upscale_ok,
        tooltip=None if upscale_ok else "Upscale blocked: 4K / ≥2160p",
    )
    check = ft.Checkbox(
        value=selected,
        on_change=lambda _e, i=item.id: on_toggle and on_toggle(i),
    )
    return ft.Container(
        bgcolor=COLORS["select"] if selected else COLORS["surface"],
        border=ft.Border.all(1, COLORS["accent"] if selected else COLORS["border"]),
        border_radius=RADIUS_CARD,
        padding=8,
        content=ft.Column(
            [
                ft.Row([check, ft.Container(expand=True), preview], spacing=4),
                ft.Text(
                    item.title or Path_name(item.path),
                    max_lines=2,
                    color=COLORS["text_primary"],
                    size=13,
                    weight=ft.FontWeight.W_500,
                ),
                ft.Text(
                    " · ".join(
                        p
                        for p in (
                            item.source or "",
                            item.resolution_label,
                            _date_label(item.date_added),
                        )
                        if p
                    ),
                    color=COLORS["text_secondary"],
                    size=11,
                    max_lines=1,
                ),
                ft.Row(
                    [
                        ft.TextButton(content="Play", on_click=lambda _e, i=item.id: on_play and on_play(i)),
                        ft.TextButton(content="Reveal", on_click=lambda _e, i=item.id: on_reveal and on_reveal(i)),
                        upscale_btn,
                    ],
                    spacing=0,
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            content="★ Fav" if item.is_favorite else "Fav",
                            on_click=lambda _e, i=item.id: on_favorite and on_favorite(i),
                        ),
                        ft.TextButton(
                            content="Later" if item.watch_later else "Watch later",
                            on_click=lambda _e, i=item.id: on_watch_later and on_watch_later(i),
                        ),
                    ],
                    spacing=0,
                ),
            ],
            spacing=4,
        ),
        data={"item_id": item.id, "job_id": item.job_id, "path": item.path},
        on_click=lambda _e, i=item.id: on_play and on_play(i),
    )


def Path_name(path: str) -> str:
    from pathlib import Path

    return Path(path).name


def onboarding_dialog(
    *,
    step: str,
    root_label: str | None,
    pending_count: int,
    sample_titles: list[str] | None = None,
    on_choose: Any,
    on_move: Any,
    on_skip: Any,
    on_close: Any,
    progress: tuple[int, int] | None = None,
    error: str | None = None,
    moving: bool = False,
    on_cancel: Any | None = None,
    progress_column: ft.Control | None = None,
    summary: str | None = None,
) -> ft.AlertDialog:
    """Two-step wizard: pick folder, then Move / Skip. Does not mark onboarded by itself."""
    sample_titles = sample_titles or []
    if step == "move" and root_label:
        title = "Moving files" if moving else ("Library move finished" if summary else "Move completed downloads")
        intro = (
            f"Library folder: {root_label}\n\n"
            f"{pending_count} file(s) from completed jobs and the download folder "
            "can be moved into Uncategorized (filenames kept). Queue items stay playable."
        )
        sample_lines = sample_titles[:8]
        if pending_count > len(sample_lines):
            sample_lines = [*sample_lines, f"… and {pending_count - len(sample_lines)} more"]
        sample = ft.Column(
            [ft.Text(t, size=12, color=COLORS["text_secondary"], max_lines=1) for t in sample_lines],
            spacing=2,
            width=460,
        )
        sample.visible = not moving and not summary
        if progress_column is not None:
            prog_ctrl: ft.Control = progress_column
            prog_ctrl.visible = bool(moving) or bool(summary)
        elif progress:
            done, total = progress
            prog_ctrl = ft.Column(
                [
                    ft.Text(f"Moving {done} of {total}…", size=12, color=COLORS["text_primary"]),
                    ft.ProgressBar(value=(done / total) if total else 0, width=420),
                ],
                spacing=6,
            )
        else:
            prog_ctrl = ft.Container(height=0, visible=False)
        err = ft.Text(error or "", color=COLORS["danger"], size=12, visible=bool(error))
        sum_txt = ft.Text(summary or "", size=12, color=COLORS["text_primary"], visible=bool(summary))
        if moving:
            actions = [
                elevated_outlined_button("Cancel", on_click=lambda _e: on_cancel and on_cancel()),
            ]
        elif summary:
            if pending_count:
                actions = [
                    elevated_outlined_button("Skip for now", on_click=lambda _e: on_skip()),
                    elevated_filled_button("Retry", on_click=lambda _e: on_move()),
                ]
            else:
                actions = [
                    elevated_filled_button("Done", on_click=lambda _e: on_close()),
                ]
        else:
            move_label = "Move to Library" if pending_count else "Finish"
            actions = [
                elevated_outlined_button("Choose different folder…", on_click=lambda _e: on_choose()),
                elevated_outlined_button("Skip for now", on_click=lambda _e: on_skip()),
                elevated_filled_button(move_label, on_click=lambda _e: on_move()),
            ]
        body = ft.Column(
            [
                ft.Text(intro, color=COLORS["text_secondary"], size=13, selectable=True),
                sample,
                prog_ctrl,
                sum_txt,
                err,
            ],
            spacing=10,
            width=460,
        )
    else:
        title = "Set up your Library"
        body = ft.Column(
            [
                ft.Text(
                    "Library lives on this PC: a folder you choose plus SQLite metadata. "
                    "Nothing is uploaded. Queue and History stay as they are — completed "
                    "items remain playable from the Queue thumbnail.",
                    color=COLORS["text_secondary"],
                    size=13,
                ),
                ft.Text("Step 1 of 2 — choose a Library folder (any drive).", size=13),
            ],
            spacing=10,
            width=460,
        )
        actions = [
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Choose folder…", on_click=lambda _e: on_choose()),
        ]
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=body,
        actions=actions,
        bgcolor=COLORS["surface"],
    )
    dlg.data = {
        "step": step,
        "move": on_move,
        "skip": on_skip,
        "pending": pending_count,
        "root": root_label,
        "sample": sample_titles,
        "progress": progress,
        "error": error,
        "moving": moving,
        "summary": summary,
        "cancel": on_cancel,
        "progress_column": progress_column,
    }
    return dlg


def new_downloads_dialog(n: int, *, on_yes: Any, on_not_now: Any) -> ft.AlertDialog:
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("New downloads"),
        content=ft.Text(
            f"{n} new download{'s' if n != 1 else ''} are not in Library yet. "
            "Move them into your Library folder?"
        ),
        actions=[
            elevated_outlined_button("Not now", on_click=lambda _e: on_not_now()),
            elevated_filled_button("Move to Library", on_click=lambda _e: on_yes()),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"count": n}
    return dlg


def duplicate_report_dialog(
    groups: list[Any],
    *,
    on_merge: Any,
    on_close: Any,
) -> ft.AlertDialog:
    lines = []
    extras = 0
    for group in groups:
        extras += len(group.extras)
        names = ", ".join(Path_name(i.path) for i in group.items)
        lines.append(names)
    body = (
        f"{len(groups)} duplicate group(s), {extras} extra file(s).\n"
        "Keep the higher-resolution / newer file. Recycle Bin for the rest.\n\n"
        + "\n".join(lines[:12])
    )
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Duplicate videos"),
        content=ft.Text(body, size=13, selectable=True),
        actions=[
            elevated_outlined_button("Keep all", on_click=lambda _e: on_close()),
            elevated_filled_button("Merge (Recycle Bin)", on_click=lambda _e: on_merge()),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"groups": len(groups), "extras": extras, "merge": on_merge}
    return dlg


def junk_triage_dialog(
    files: list[Any],
    *,
    on_recycle: Any,
    on_keep: Any,
    on_move: Any,
) -> ft.AlertDialog:
    lines = [f"{j.reason}: {j.path.name}" for j in files[:20]]
    body = ft.Text(
        f"{len(files)} junk file(s). Delete uses Recycle Bin only.\n\n" + "\n".join(lines),
        size=13,
        selectable=True,
    )
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Junk files"),
        content=body,
        actions=[
            elevated_outlined_button("Keep", on_click=lambda _e: on_keep()),
            elevated_outlined_button("Move…", on_click=lambda _e: on_move()),
            elevated_filled_button("Delete (Recycle Bin)", on_click=lambda _e: on_recycle()),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"count": len(files), "recycle": on_recycle, "keep": on_keep, "move": on_move}
    return dlg


def add_to_collection_dialog(
    collections: list[Any],
    *,
    on_apply: Any,
    on_close: Any,
) -> ft.AlertDialog:
    boxes = [
        ft.Checkbox(label=c.name, data={"id": c.id, "kind": c.kind}, value=False)
        for c in collections
        if c.kind in {"type", "custom", "subject"}
    ]

    def apply(_e=None) -> None:
        ids = [int(b.data["id"]) for b in boxes if b.value]
        on_apply(ids)

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Add to collection"),
        content=ft.Column(boxes, spacing=4, scroll=ft.ScrollMode.AUTO, height=320, width=360),
        actions=[
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Apply", on_click=apply),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"boxes": boxes, "apply": apply}
    return dlg


def create_collection_dialog(*, on_create: Any, on_close: Any) -> ft.AlertDialog:
    field = ft.TextField(label="Collection name", autofocus=True, width=320)

    def save(_e=None) -> None:
        on_create(field.value or "")

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("New collection"),
        content=field,
        actions=[
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Create", on_click=save),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"field": field, "save": save}
    return dlg


def send_private_dialog(
    n: int,
    *,
    disguise_default: str,
    on_confirm: Any,
    on_close: Any,
) -> ft.AlertDialog:
    disguise = ft.Checkbox(label=f"Disguise extension ({disguise_default})", value=False)
    note = ft.Text(
        "Copies only — originals stay until you choose Keep, Recycle Bin, or Move. "
        "Password protects the zip contents. A renamed extension hides the file from "
        "casual browsing; this is not remote security.",
        color=COLORS["text_secondary"],
        size=12,
    )

    def go(_e=None) -> None:
        on_confirm(bool(disguise.value))

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text(f"Send {n} item(s) to Private"),
        content=ft.Column([note, disguise], spacing=10, width=440),
        actions=[
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Copy and pack", on_click=go),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"disguise": disguise}
    return dlg


def private_disposition_dialog(*, on_keep: Any, on_trash: Any, on_move: Any) -> ft.AlertDialog:
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Originals"),
        content=ft.Text(
            "Private copies are packed. What should happen to the Library originals?"
        ),
        actions=[
            elevated_outlined_button("Keep", on_click=lambda _e: on_keep()),
            elevated_outlined_button("Delete (Recycle Bin)", on_click=lambda _e: on_trash()),
            elevated_filled_button("Move to folder…", on_click=lambda _e: on_move()),
        ],
        bgcolor=COLORS["surface"],
    )
    return dlg


def confirm_remove_dialog(n: int, *, delete_files: bool, on_yes: Any, on_close: Any) -> ft.AlertDialog:
    if delete_files:
        title = "Delete files"
        body = (
            f"Delete {n} file(s) from disk (Recycle Bin on Windows) and remove them from Library? "
            "This does not affect the download queue rows."
        )
    else:
        title = "Remove from Library"
        body = (
            f"Remove {n} item(s) from the Library index only? Files stay on disk."
        )
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text(title),
        content=ft.Text(body),
        actions=[
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Confirm", on_click=lambda _e: on_yes()),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"delete_files": delete_files, "count": n}
    return dlg


def confirm_reset_library_dialog(*, on_yes: Any, on_close: Any) -> ft.AlertDialog:
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Reset Library onboarding"),
        content=ft.Text(
            "Clear the Library index, collections, and onboarding flags so first-run setup "
            "runs again. Media files on disk are not deleted."
        ),
        actions=[
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Reset onboarding", on_click=lambda _e: on_yes()),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"kind": "reset_library"}
    return dlg


def private_password_dialog(
    *,
    title: str,
    on_submit: Any,
    on_close: Any,
    confirm: bool = False,
    note: str = "",
) -> ft.AlertDialog:
    pw = ft.TextField(label="Password", password=True, width=320)
    pw2 = ft.TextField(label="Confirm password", password=True, width=320, visible=confirm)
    hint = ft.Text(
        note
        or "Local hash only. Forgotten password cannot be emailed. This is not remote security.",
        color=COLORS["text_secondary"],
        size=12,
    )

    def go(_e=None) -> None:
        if confirm and (pw.value or "") != (pw2.value or ""):
            hint.value = "Passwords do not match."
            hint.color = COLORS["danger"]
            return
        on_submit(pw.value or "")

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text(title),
        content=ft.Column([hint, pw, pw2], spacing=8, width=360),
        actions=[
            elevated_outlined_button("Cancel", on_click=lambda _e: on_close()),
            elevated_filled_button("Unlock" if not confirm else "Save", on_click=go),
        ],
        bgcolor=COLORS["surface"],
    )
    dlg.data = {"password": pw, "confirm": pw2, "submit": go}
    return dlg


def build_library_toolbar(
    *,
    count: int,
    search: str,
    sort: str,
    source: str | None,
    flag: str | None,
    on_search: Any,
    on_sort: Any,
    on_source: Any,
    on_flag: Any,
    on_new_collection: Any,
    on_add_collection: Any,
    on_move_new: Any | None,
    pending_new: int,
    has_selection: bool,
    on_bulk_upscale: Any | None = None,
    on_bulk_remove: Any | None = None,
    on_bulk_delete: Any | None = None,
    on_send_private: Any | None = None,
    on_scan: Any | None = None,
    orphan_count: int = 0,
    on_dedupe: Any | None = None,
    on_junk: Any | None = None,
) -> ft.Column:
    search_field = ft.TextField(
        hint_text="Search title",
        value=search,
        on_submit=lambda e: on_search(e.control.value or ""),
        on_blur=lambda e: on_search(e.control.value or ""),
        width=220,
    )
    sort_menu = ft.PopupMenuButton(
        items=[
            ft.PopupMenuItem(content="Date", on_click=lambda _e: on_sort("date")),
            ft.PopupMenuItem(content="Title", on_click=lambda _e: on_sort("title")),
            ft.PopupMenuItem(content="Resolution", on_click=lambda _e: on_sort("resolution")),
            ft.PopupMenuItem(content="Source", on_click=lambda _e: on_sort("source")),
        ],
        tooltip=f"Sort: {sort}",
    )
    source_items = [ft.PopupMenuItem(content="All sources", on_click=lambda _e: on_source(None))]
    source_items.extend(
        ft.PopupMenuItem(content=s, on_click=lambda _e, label=s: on_source(label)) for s in SOURCES
    )
    source_menu = ft.PopupMenuButton(items=source_items, tooltip=f"Source: {source or 'All'}")
    flag_items = [ft.PopupMenuItem(content="All flags", on_click=lambda _e: on_flag(None))]
    flag_items.extend(
        ft.PopupMenuItem(content=f, on_click=lambda _e, label=f: on_flag(label)) for f in SYSTEM_FLAGS
    )
    flag_menu = ft.PopupMenuButton(items=flag_items, tooltip=f"Flag: {flag or 'All'}")
    move_btn = elevated_outlined_button(
        f"Move {pending_new} new",
        on_click=lambda _e: on_move_new and on_move_new(),
    )
    move_btn.visible = pending_new > 0
    scan_btn = elevated_outlined_button(
        f"Scan library folder ({orphan_count})",
        on_click=lambda _e: on_scan and on_scan(),
    )
    scan_btn.visible = orphan_count > 0
    add_btn = elevated_outlined_button(
        "Add to collection…",
        on_click=lambda _e: on_add_collection(),
    )
    add_btn.disabled = not has_selection
    upscale_bulk = elevated_outlined_button("Upscale eligible", on_click=lambda _e: on_bulk_upscale and on_bulk_upscale())
    upscale_bulk.disabled = not has_selection
    remove_btn = elevated_outlined_button("Remove from library", on_click=lambda _e: on_bulk_remove and on_bulk_remove())
    remove_btn.disabled = not has_selection
    delete_btn = elevated_outlined_button("Delete files…", on_click=lambda _e: on_bulk_delete and on_bulk_delete())
    delete_btn.disabled = not has_selection
    private_btn = elevated_outlined_button("Send to Private", on_click=lambda _e: on_send_private and on_send_private())
    private_btn.disabled = not has_selection
    row = ft.Row(
        [
            ft.Text(f"{count} in Library", color=COLORS["text_secondary"], size=13),
            search_field,
            ft.Text(f"Sort: {sort}", size=12, color=COLORS["text_secondary"]),
            sort_menu,
            source_menu,
            flag_menu,
            ft.Container(expand=True),
            move_btn,
            scan_btn,
            elevated_outlined_button("Duplicates…", on_click=lambda _e: on_dedupe and on_dedupe()),
            elevated_outlined_button("Junk files…", on_click=lambda _e: on_junk and on_junk()),
            elevated_outlined_button("New collection", on_click=lambda _e: on_new_collection()),
            add_btn,
            upscale_bulk,
            remove_btn,
            delete_btn,
            private_btn,
        ],
        spacing=8,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    row.data = {
        "search": search_field,
        "sort": sort_menu,
        "source": source_menu,
        "flag": flag_menu,
        "move": move_btn,
        "scan": scan_btn,
        "add": add_btn,
        "count": count,
        "orphan_count": orphan_count,
    }
    return ft.Column([row], spacing=4, data={"count": count, "orphan_count": orphan_count})
