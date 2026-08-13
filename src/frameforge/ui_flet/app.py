"""Flet desktop shell — light FrameForge window."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.paths import db_path, ensure_output_tree
from frameforge.pipeline import build_worker
from frameforge.ui_flet.bridge import UiBridge
from frameforge.ui_flet.components.job_card import (
    build_floating_bar,
    build_job_card,
    empty_queue_state,
)
from frameforge.ui_flet.components.settings_dialog import build_settings_dialog
from frameforge.ui_flet.components.status_pill import status_from_repo
from frameforge.ui_flet.job_view import floating_bar_view, structural_sig
from frameforge.ui_flet.theme import (
    COLORS,
    FONT_FAMILY,
    TAB_LABELS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)


def apply_page_chrome(page: ft.Page) -> None:
    page.title = "FrameForge"
    page.bgcolor = COLORS["app_bg"]
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.theme = ft.Theme(font_family=FONT_FAMILY, color_scheme_seed=COLORS["accent"])
    window = getattr(page, "window", None)
    if window is not None:
        window.width = WINDOW_WIDTH
        window.height = WINDOW_HEIGHT
        window.min_width = 900
        window.min_height = 600


def _placeholder_panel(label: str) -> ft.Container:
    return ft.Container(
        expand=True,
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=12,
        padding=24,
        content=ft.Text(
            f"{label} placeholder",
            color=COLORS["text_secondary"],
            size=14,
        ),
    )


def build_header(
    *,
    status_text: str = "Idle • 0 ready",
    on_settings: Any | None = None,
    on_authenticate: Any | None = None,
) -> ft.Row:
    return ft.Row(
        [
            ft.Text(
                "FrameForge",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=COLORS["text_primary"],
            ),
            ft.Container(expand=True),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor=COLORS["surface"],
                border=ft.Border.all(1, COLORS["border"]),
                border_radius=999,
                content=ft.Text(status_text, color=COLORS["text_secondary"], size=13),
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.SETTINGS_OUTLINED,
                tooltip="Settings",
                icon_color=COLORS["text_primary"],
                on_click=on_settings,
            ),
            ft.IconButton(
                icon=ft.Icons.SHIELD_OUTLINED,
                tooltip="Authenticate",
                icon_color=COLORS["text_primary"],
                on_click=on_authenticate,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def build_hero(*, on_add: Any | None = None, on_import: Any | None = None) -> ft.Row:
    url = ft.TextField(
        hint_text="Paste video URL or drop link here...",
        expand=True,
        border_color=COLORS["border"],
        focused_border_color=COLORS["accent"],
        prefix_icon=ft.Icons.LINK,
    )
    add = ft.FilledButton(
        content="+ Add to Queue",
        bgcolor=COLORS["accent"],
        color="#FFFFFF",
        on_click=on_add,
    )
    imp = ft.OutlinedButton(content="Import TXT/MD", icon=ft.Icons.UPLOAD_FILE, on_click=on_import)
    row = ft.Row([url, add, imp], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    row.data = {"url": url, "add": add, "import": imp}
    return row


def build_tabs(
    queue: ft.Control | None = None,
    history: ft.Control | None = None,
    thumbs: ft.Control | None = None,
) -> ft.Tabs:
    views = [
        queue or _placeholder_panel("Queue"),
        history or _placeholder_panel("History"),
        thumbs or _placeholder_panel("Thumbnails"),
    ]
    return ft.Tabs(
        length=len(TAB_LABELS),
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[ft.Tab(label=name) for name in TAB_LABELS],
                    label_color=COLORS["accent"],
                    unselected_label_color=COLORS["text_secondary"],
                    indicator_color=COLORS["accent"],
                    divider_color=COLORS["border"],
                ),
                ft.TabBarView(expand=True, controls=views),
            ],
        ),
    )


class FrameForgeUi:
    """Flet presentation + UiBridge. Worker is idle until Download / Retry."""

    def __init__(
        self,
        repo: JobRepository | None = None,
        *,
        start_worker: bool = False,
        recover_on_launch: bool = True,
        worker: Any | None = None,
    ) -> None:
        ensure_output_tree()
        self.repo = repo or JobRepository(db_path())
        self.worker = worker or build_worker(self.repo)
        self.bridge = UiBridge(self.repo, self.worker)
        if recover_on_launch:
            self.worker.prepare_idle_launch()
        if start_worker:
            self.worker.request_download_all()
        self.page: ft.Page | None = None
        self.settings_dialog: ft.AlertDialog | None = None
        self.settings_focus_count = 0
        self.auth_open = False
        self.header: ft.Row | None = None
        self.hero: ft.Row | None = None
        self.tabs: ft.Tabs | None = None
        self.selected_ids: set[int] = set()
        self.expanded_failed: set[int] = set()
        self.queue_list: ft.ListView | None = None
        self.history_list: ft.ListView | None = None
        self.thumbs_grid: ft.GridView | None = None
        self.floating: ft.Container | None = None
        self.resource_banner: ft.Container | None = None
        self._queue_sig: tuple[Any, ...] | None = None
        self.fail_pause_payload: dict[str, Any] | None = None
        self.fail_pause_shown = 0
        self.history_status: str | None = None
        self.history_domain: str | None = None
        self.history_search: str = ""
        self.bridge.set_fail_pause_handler(self._on_fail_pause)

    def _on_fail_pause(self, job: Any, payload: dict[str, Any]) -> None:
        self.fail_pause_payload = payload
        self.fail_pause_shown += 1
        if self.page is not None:
            self.page.show_dialog(self._fail_pause_dialog(payload))
            self.page.update()

    def _fail_pause_dialog(self, payload: dict[str, Any]) -> ft.AlertDialog:
        jid = int(payload["job_id"])

        def act(aid: str):
            def _(_e=None):
                self.bridge.handle_fail_pause_action(aid, jid)
                if self.page is not None:
                    self.page.pop_dialog()
                self.refresh_queue()

            return _

        return ft.AlertDialog(
            modal=True,
            title=ft.Text("Queue paused"),
            content=ft.Column(
                [
                    ft.Text(str(payload.get("title") or "")),
                    ft.Text(str(payload.get("url") or ""), color=COLORS["text_secondary"]),
                    ft.Text(f"Cause: {payload.get('cause') or ''}", color=COLORS["warn"]),
                ],
                spacing=8,
                width=460,
            ),
            actions=[
                ft.FilledButton(content="Import from browser", on_click=act("import_browser")),
                ft.OutlinedButton(content="Authenticate site", on_click=act("authenticate")),
                ft.OutlinedButton(content="Retry this job", on_click=act("retry")),
                ft.OutlinedButton(content="Skip & resume queue", on_click=act("skip_resume")),
                ft.OutlinedButton(content="Stop queue", on_click=act("stop")),
            ],
        )

    def build(self) -> ft.Column:
        status = status_from_repo(self.repo, self.worker)
        self.header = build_header(
            status_text=status,
            on_settings=lambda _e=None: self.open_settings(),
            on_authenticate=lambda _e=None: self.open_authenticate(),
        )
        self.hero = build_hero(
            on_add=lambda _e=None: self.add_url(),
            on_import=lambda _e=None: self.import_file(),
        )
        self.resource_banner = ft.Container(visible=False, data={"text": ""})
        self.queue_list = ft.ListView(expand=True, spacing=8, padding=4)
        self.history_list = ft.ListView(expand=True, spacing=8, padding=4)
        self.thumbs_grid = ft.GridView(expand=True, runs_count=4, max_extent=220, spacing=8)
        self.floating = ft.Container(visible=False)
        queue_body = ft.Column(
            [self.queue_list, self.floating],
            expand=True,
            spacing=8,
        )
        hist_filters = ft.Row(
            [
                ft.TextButton(content="All", on_click=lambda _e: self.set_history_filter(None)),
                ft.TextButton(content="Completed", on_click=lambda _e: self.set_history_filter("completed")),
                ft.TextButton(content="Failed", on_click=lambda _e: self.set_history_filter("failed")),
                ft.OutlinedButton(
                    content="Re-download selected",
                    on_click=lambda _e: self.redownload_history(),
                ),
                ft.OutlinedButton(
                    content="Clear selected",
                    on_click=lambda _e: self.clear_history_selected(),
                ),
            ]
        )
        history_body = ft.Column([hist_filters, self.history_list], expand=True)
        self.tabs = build_tabs(queue_body, history_body, self.thumbs_grid)
        root = ft.Column(
            expand=True,
            spacing=16,
            controls=[self.header, self.hero, self.resource_banner, self.tabs],
        )
        self.refresh_queue(force=True)
        self.refresh_history()
        self.refresh_thumbs()
        return root

    def queue_jobs(self) -> list[Any]:
        return list(self.repo.list_jobs())

    def toggle_select(self, job_id: int) -> None:
        if job_id in self.selected_ids:
            self.selected_ids.discard(job_id)
        else:
            self.selected_ids.add(job_id)
        self._sync_floating()
        self.refresh_queue(force=True)

    def _sync_floating(self) -> None:
        spec = floating_bar_view(self.queue_jobs(), self.selected_ids)
        if self.floating is None:
            return
        if spec is None:
            self.floating.visible = False
            self.floating.content = None
            self.floating.data = None
            return
        self.floating.visible = True
        self.floating.content = build_floating_bar(
            spec,
            on_download=self.download_selected,
            on_upscale=self.upscale_selected,
            on_convert=self.convert_selected,
            on_more=self._on_more,
        ).content
        self.floating.data = spec

    def refresh_queue(self, *, force: bool = False) -> None:
        jobs = self.queue_jobs()
        sig = structural_sig(jobs)
        active = next((j for j in jobs if j.status in {"downloading", "upscaling", "converting"}), None)
        if not force and sig == self._queue_sig and self.queue_list is not None:
            if active is not None:
                self.update_active_progress(active)
            return
        self._queue_sig = sig
        if self.queue_list is None:
            return
        if not jobs:
            self.queue_list.controls = [empty_queue_state()]
        else:
            self.queue_list.controls = [
                build_job_card(
                    job,
                    selected=job.id in self.selected_ids,
                    expanded=job.id in self.expanded_failed,
                    show_progress=active is not None and job.id == active.id,
                    on_toggle=self.toggle_select,
                    on_retry=self.retry_failed_job,
                    on_reauth=self.reauthenticate_job,
                    on_expand=self.toggle_failed_expand,
                    on_overflow=self.handle_overflow,
                )
                for job in jobs
            ]
        self._sync_floating()
        if self.page is not None:
            self.page.update()

    def update_active_progress(self, job: Any) -> None:
        if self.queue_list is None:
            return
        for card in self.queue_list.controls:
            data = getattr(card, "data", None) or {}
            if data.get("job_id") == job.id:
                data["view"] = {**(data.get("view") or {}), "progress": float(job.progress)}
                card.data = data
                return

    def toggle_failed_expand(self, job_id: int) -> None:
        if job_id in self.expanded_failed:
            self.expanded_failed.discard(job_id)
        else:
            self.expanded_failed.add(job_id)
        self.refresh_queue(force=True)

    def retry_failed_job(self, job_id: int) -> None:
        self.bridge.retry_job(job_id)
        self.refresh_queue(force=True)

    def reauthenticate_job(self, job_id: int) -> None:
        self.bridge.handle_fail_pause_action("authenticate", job_id)
        self.auth_open = True

    def download_selected(self) -> None:
        self.bridge.download_selected(sorted(self.selected_ids))
        self.refresh_queue(force=True)

    def upscale_selected(self) -> None:
        from frameforge.gui.actions import can_upscale

        ids = [i for i in self.selected_ids if can_upscale(self.repo.get(i)) and not self.repo.get(i).upscale_blocked]
        for jid in ids:
            self.worker.request_upscale_ids([jid]) if hasattr(self.worker, "request_upscale_ids") else None
        self.refresh_queue(force=True)

    def convert_selected(self) -> None:
        if hasattr(self.worker, "request_convert_ids"):
            self.worker.request_convert_ids(sorted(self.selected_ids))
        self.refresh_queue(force=True)

    def handle_overflow(self, job_id: int, action: str) -> None:
        if action == "retry":
            self.retry_failed_job(job_id)
        elif action == "remove_from_queue":
            self.repo.clear_from_queue([job_id])
            self.selected_ids.discard(job_id)
            self.refresh_queue(force=True)
        elif action == "upscale":
            self.selected_ids = {job_id}
            self.upscale_selected()
        elif action == "convert":
            self.selected_ids = {job_id}
            self.convert_selected()
        elif action == "set_format":
            self._format_job_ids = [job_id]
            self.format_open = True
        else:
            self._last_overflow = (job_id, action)

    def _on_more(self, action: str) -> None:
        if action == "clear_finished":
            self.repo.clear_finished_from_queue()
        elif action == "clear_selected":
            self.repo.clear_from_queue(sorted(self.selected_ids))
            self.selected_ids.clear()
        elif action == "select_recommended":
            self.selected_ids = {
                j.id for j in self.queue_jobs() if j.upscale_recommended and j.status == "completed"
            }
        elif action == "download_all":
            self.bridge.download_all_pending()
        elif action == "set_format":
            self.format_open = True
            self._format_job_ids = sorted(self.selected_ids)
        self.refresh_queue(force=True)

    def set_history_filter(self, status: str | None) -> None:
        self.history_status = status
        self.refresh_history()

    def refresh_history(self) -> None:
        jobs = self.repo.list_history(
            status=self.history_status,
            search=self.history_search or None,
            domain=self.history_domain,
        )
        if self.history_list is None:
            return
        self.history_list.controls = [
            build_job_card(
                job,
                selected=job.id in self.selected_ids,
                expanded=False,
                show_progress=False,
                on_toggle=self.toggle_select,
            )
            for job in jobs
        ]
        if self.page is not None:
            self.page.update()

    def redownload_history(self) -> list[int]:
        ids = sorted(self.selected_ids)
        new_ids = self.repo.reenqueue_as_pending(ids) if ids else []
        self.refresh_queue(force=True)
        self.refresh_history()
        return new_ids

    def clear_history_selected(self) -> None:
        if self.selected_ids:
            self.repo.clear_history(sorted(self.selected_ids))
        self.refresh_history()

    def refresh_thumbs(self) -> None:
        if self.thumbs_grid is None:
            return
        cells = []
        for job in self.repo.list_history():
            cells.append(
                ft.Container(
                    bgcolor=COLORS["surface"],
                    border=ft.Border.all(1, COLORS["border"]),
                    border_radius=12,
                    padding=8,
                    content=ft.Column(
                        [
                            ft.Text(f"#{job.id}", color=COLORS["text_secondary"], size=11),
                            ft.Text(job.title or job.url, max_lines=2, color=COLORS["text_primary"]),
                        ]
                    ),
                    data={"job_id": job.id},
                )
            )
        self.thumbs_grid.controls = cells

    def set_resource_banner(self, text: str | None) -> None:
        if self.resource_banner is None:
            return
        self.resource_banner.visible = bool(text)
        self.resource_banner.data = {"text": text or ""}
        self.resource_banner.content = ft.Text(text or "", color=COLORS["warn"]) if text else None

    def open_format_modal(self, job_ids: list[int] | None = None) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import format_dialog

        ids = list(job_ids or sorted(self.selected_ids))
        self.format_open = True
        self._format_job_ids = ids

        def apply(label: str) -> None:
            for jid in ids:
                self.repo.set_format_preference(jid, label)
            self.format_open = False

        self.format_dialog = format_dialog(on_apply=apply, on_cancel=lambda _e=None: setattr(self, "format_open", False))
        return self.format_dialog

    def open_bulk_confirm(self, new_count: int, dup_count: int) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import bulk_import_dialog

        self.bulk_open = True
        self.bulk_dialog = bulk_import_dialog(
            new_count,
            dup_count,
            on_add=lambda _e=None: setattr(self, "bulk_open", False),
            on_cancel=lambda _e=None: setattr(self, "bulk_open", False),
        )
        return self.bulk_dialog

    def open_playlist_modal(self, title: str, entries: list[Any]) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import playlist_dialog

        self.playlist_open = True
        self.playlist_dialog = playlist_dialog(
            title,
            entries,
            on_enqueue=lambda _e=None: setattr(self, "playlist_open", False),
            on_cancel=lambda _e=None: setattr(self, "playlist_open", False),
        )
        return self.playlist_dialog

    def open_quit_busy(self) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import quit_busy_dialog

        self.quit_choice: str | None = None

        def choose(c: str) -> None:
            self.quit_choice = c

        self.quit_dialog = quit_busy_dialog(on_choice=choose, on_cancel=lambda _e=None: None)
        return self.quit_dialog

    def add_url(self) -> Any | None:
        field = (self.hero.data or {}).get("url") if self.hero is not None else None
        url = (getattr(field, "value", None) or "").strip()
        if not url:
            return None
        job = self.bridge.enqueue_url(url)
        if field is not None:
            field.value = ""
        self.refresh_queue(force=True)
        if self.page is not None:
            self.page.update()
        return job

    def import_file(self) -> None:
        """Placeholder until Phase E bulk-import modal; enqueue is never auto-started."""
        self._pending_import = True

    def open_authenticate(self, prefill: str | None = None) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import authenticate_dialog
        from urllib.parse import urlparse

        self.auth_open = True
        host = ""
        if prefill:
            host = urlparse(prefill).hostname or prefill
        self.auth_dialog = authenticate_dialog(
            host or "site",
            on_firefox=lambda _e=None: None,
            on_txt=lambda _e=None: None,
            on_close=lambda _e=None: setattr(self, "auth_open", False),
        )
        if self.page is not None:
            self.page.show_dialog(self.auth_dialog)
            self.page.update()
        return self.auth_dialog

    def open_settings(self) -> ft.AlertDialog:
        if self.bridge.settings_open and self.settings_dialog is not None:
            self.settings_focus_count += 1
            if self.page is not None:
                self.page.show_dialog(self.settings_dialog)
                self.page.update()
            return self.settings_dialog

        def on_close(_e=None) -> None:
            self.bridge.settings_open = False
            if self.page is not None:
                self.page.pop_dialog()
                self.page.update()

        self.settings_dialog = build_settings_dialog(
            self.repo,
            on_close=on_close,
        )
        self.bridge.settings_open = True
        if self.page is not None:
            self.page.show_dialog(self.settings_dialog)
            self.page.update()
        return self.settings_dialog

    def attach_page(self, page: ft.Page) -> None:
        self.page = page
        apply_page_chrome(page)
        page.add(self.build())

    def shutdown(self) -> None:
        try:
            self.worker.stop(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.repo.close()
        except Exception:  # noqa: BLE001
            pass


def build_header_default() -> ft.Row:
    return build_header()


def build_shell() -> ft.Column:
    """Light chrome: header + hero + Queue/History/Thumbnails placeholders (no backend)."""
    return ft.Column(
        expand=True,
        spacing=16,
        controls=[build_header(), build_hero(), build_tabs()],
    )


def create_ui(**kwargs: Any) -> FrameForgeUi:
    kwargs.setdefault("recover_on_launch", True)
    kwargs.setdefault("start_worker", False)
    return FrameForgeUi(**kwargs)


def main(page: ft.Page) -> None:
    ui = create_ui()
    ui.attach_page(page)


def run_gui(**kwargs: Any) -> None:
    ui = create_ui(**kwargs)

    def _main(page: ft.Page) -> None:
        ui.attach_page(page)

    ft.app(_main)
