"""Flet desktop shell — light FrameForge window."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import flet as ft

from frameforge import __version__
from frameforge.db.repository import JobRepository
from frameforge.paths import db_path, ensure_output_tree
from frameforge.pipeline import build_worker
from frameforge.ui_flet.bridge import UiBridge
from frameforge.ui_flet.components.job_card import (
    build_floating_bar,
    build_job_card,
    build_queue_chrome,
    empty_queue_state,
)
from frameforge.ui_flet.components.settings_dialog import build_settings_dialog
from frameforge.ui_flet.components.status_pill import status_from_repo
from frameforge.ui_flet.dialog_host import DialogHost
from frameforge.ui_flet.job_view import floating_bar_view, structural_sig
from frameforge.ui_flet.queue_chrome import queue_chrome_spec
from frameforge.ui_flet.elevation import elevated_filled_button, elevated_outlined_button
from frameforge.ui_flet.theme import (
    COLORS,
    FONT_FAMILY,
    TAB_LABELS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)

_GUI_RUNNING = False


def apply_page_chrome(page: ft.Page) -> None:
    """Opaque native window + no DWM shadow — avoids the Windows drag ghost copy."""
    page.title = f"FrameForge {__version__}"
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
        window.bgcolor = COLORS["app_bg"]
        window.opacity = 1.0
        window.shadow = False
        window.title_bar_hidden = False
        window.frameless = False
        window.visible = True
        window.ignore_mouse_events = False


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
    add = elevated_filled_button("+ Add to Queue", on_click=on_add)
    imp = elevated_outlined_button("Import TXT/MD", on_click=on_import, icon=ft.Icons.UPLOAD_FILE)
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
        self.dialogs = DialogHost(self)
        self.settings_dialog: ft.AlertDialog | None = None
        self.settings_focus_count = 0
        self.auth_open = False
        self.format_open = False
        self.bulk_open = False
        self.playlist_open = False
        self.header: ft.Row | None = None
        self.hero: ft.Row | None = None
        self.tabs: ft.Tabs | None = None
        self.selected_ids: set[int] = set()
        self.expanded_failed: set[int] = set()
        self.queue_list: ft.ListView | None = None
        self.queue_chrome: ft.Container | None = None
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
        self.file_picker: ft.FilePicker | None = None
        self.reveal_launch = True
        self.exit_process_on_quit = False
        self._shutdown_complete = False
        self._import_preview: Any | None = None
        self._pending_import = False
        self._browser_cookie_runner: Any | None = None
        self.import_browser_fn: Any | None = None
        self.last_more_action: str | None = None
        self.more_invocations: list[str] = []
        self.bridge.set_fail_pause_handler(self._on_fail_pause)

    def close_dialog(self, _e: Any = None) -> None:
        self.dialogs.close(_e)

    def _on_fail_pause(self, job: Any, payload: dict[str, Any]) -> None:
        self.fail_pause_payload = payload
        self.fail_pause_shown += 1
        if self.page is not None:
            self.dialogs.open("fail_pause", self._fail_pause_dialog(payload))

    def _fail_pause_dialog(self, payload: dict[str, Any]) -> ft.AlertDialog:
        jid = int(payload["job_id"])

        def act(aid: str):
            def _(_e=None):
                if aid == "authenticate":
                    url = payload.get("url")
                    self.close_dialog()
                    self.open_authenticate(prefill=url)
                    return
                if aid == "import_browser":
                    url = str(payload.get("url") or "")
                    if url:
                        self.import_cookies_from_browser_for_site(url, browser="firefox")
                    self.bridge.handle_fail_pause_action(aid, jid)
                    self.close_dialog()
                    self.refresh_queue()
                    return
                self.bridge.handle_fail_pause_action(aid, jid)
                self.close_dialog()
                self.refresh_queue()

            return _

        return ft.AlertDialog(
            modal=False,
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
                elevated_filled_button("Import from browser", on_click=act("import_browser")),
                elevated_outlined_button("Authenticate site", on_click=act("authenticate")),
                elevated_outlined_button("Retry this job", on_click=act("retry")),
                elevated_outlined_button("Skip & resume queue", on_click=act("skip_resume")),
                elevated_outlined_button("Stop queue", on_click=act("stop")),
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
        self.queue_chrome = ft.Container(visible=False)
        self.queue_list = ft.ListView(expand=True, spacing=8, padding=4)
        self.history_list = ft.ListView(expand=True, spacing=8, padding=4)
        self.thumbs_grid = ft.GridView(expand=True, runs_count=4, max_extent=220, spacing=8)
        self.floating = ft.Container(visible=False)
        queue_body = ft.Column(
            [self.queue_chrome, self.queue_list, self.floating],
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

    def _sync_queue_chrome(self) -> None:
        spec = queue_chrome_spec(self.queue_jobs(), self.selected_ids)
        if self.queue_chrome is None:
            return
        built = build_queue_chrome(
            spec,
            on_download_all=self.download_all_pending,
            on_retry_failed=self.retry_all_failed,
            on_clear_finished=self.clear_finished,
            on_clear_selected=self.clear_selected,
        )
        self.queue_chrome.visible = built.visible
        self.queue_chrome.content = built.content
        self.queue_chrome.data = spec

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
            on_clear=self.clear_selected,
            on_retry=self.retry_selected_failed,
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
        self._sync_queue_chrome()
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

    def retry_all_failed(self) -> list[int]:
        ids = self.bridge.retry_all_failed()
        self.refresh_queue(force=True)
        return ids

    def retry_selected_failed(self) -> list[int]:
        ids = self.bridge.retry_failed_ids(sorted(self.selected_ids))
        self.refresh_queue(force=True)
        return ids

    def download_all_pending(self) -> None:
        self.bridge.download_all_pending()
        self.refresh_queue(force=True)

    def clear_finished(self) -> None:
        self.repo.clear_finished_from_queue()
        self.selected_ids.clear()
        self.refresh_queue(force=True)

    def clear_selected(self) -> None:
        if not self.selected_ids:
            return
        self.repo.clear_from_queue(sorted(self.selected_ids))
        self.selected_ids.clear()
        self.refresh_queue(force=True)

    def reauthenticate_job(self, job_id: int) -> None:
        job = self.repo.get(job_id)
        self.open_authenticate(prefill=job.url)

    def download_selected(self) -> None:
        self.bridge.download_selected(sorted(self.selected_ids))
        self.refresh_queue(force=True)

    def upscale_selected(self) -> None:
        from frameforge.gui.actions import can_upscale

        ids = [
            i
            for i in self.selected_ids
            if can_upscale(self.repo.get(i)) and not self.repo.get(i).upscale_blocked
        ]
        if ids and hasattr(self.worker, "request_upscale_ids"):
            self.worker.request_upscale_ids(ids)
        self.refresh_queue(force=True)

    def convert_selected(self) -> None:
        if hasattr(self.worker, "request_convert_ids"):
            self.worker.request_convert_ids(sorted(self.selected_ids))
        self.refresh_queue(force=True)

    def open_folder_selected(self) -> None:
        from frameforge.util.reveal import RevealError, open_job_folder

        ids = sorted(self.selected_ids)
        if not ids:
            return
        job = self.repo.get(ids[0])
        try:
            open_job_folder(job, launch=self.reveal_launch)
        except RevealError:
            pass

    def reveal_file_selected(self) -> None:
        from frameforge.util.reveal import RevealError, reveal_job_file

        ids = sorted(self.selected_ids)
        if not ids:
            return
        job = self.repo.get(ids[0])
        try:
            reveal_job_file(job, launch=self.reveal_launch)
        except RevealError:
            pass

    def select_recommended(self) -> None:
        self.selected_ids = {
            j.id for j in self.queue_jobs() if j.upscale_recommended and j.status == "completed"
        }
        self.refresh_queue(force=True)

    def handle_overflow(self, job_id: int, action: str) -> None:
        self.selected_ids = {job_id}
        if action == "retry":
            self.retry_failed_job(job_id)
        elif action == "remove_from_queue":
            self.clear_selected()
        elif action == "upscale":
            self.upscale_selected()
        elif action == "convert":
            self.convert_selected()
        elif action == "set_format":
            self.open_format_modal([job_id])
        elif action == "open_folder":
            self.open_folder_selected()
        elif action == "reveal_file":
            self.reveal_file_selected()
        else:
            self._last_overflow = (job_id, action)

    def _on_more(self, action: str) -> None:
        self.last_more_action = action
        self.more_invocations.append(action)
        handlers = {
            "clear_finished": self.clear_finished,
            "clear_selected": self.clear_selected,
            "select_recommended": self.select_recommended,
            "download_all": self.download_all_pending,
            "download_selected": self.download_selected,
            "set_format": lambda: self.open_format_modal(sorted(self.selected_ids)),
            "upscale": self.upscale_selected,
            "convert": self.convert_selected,
            "retry_selected": self.retry_selected_failed,
            "open_folder": self.open_folder_selected,
            "reveal_file": self.reveal_file_selected,
        }
        fn = handlers.get(action)
        if fn is None:
            raise ValueError(f"unwired More action: {action}")
        fn()

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

    def _default_format(self) -> str:
        return self.repo.get_setting("format_preference", "best") or "best"

    def _default_upscale(self) -> bool:
        return self.repo.get_setting("upscale_after_download", "0") == "1"

    def open_format_modal(self, job_ids: list[int] | None = None) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import format_dialog

        ids = list(job_ids or sorted(self.selected_ids))
        self._format_job_ids = ids

        def apply(label: str) -> None:
            for jid in ids:
                self.repo.set_format_preference(jid, label)
            self.close_dialog()

        self.format_dialog = format_dialog(on_apply=apply, on_cancel=self.close_dialog)
        return self.dialogs.open("format", self.format_dialog)

    def open_bulk_confirm(
        self,
        new_count: int,
        dup_count: int,
        preview: Any | None = None,
    ) -> ft.AlertDialog:
        from frameforge.download.bulk_import import confirm_add
        from frameforge.ui_flet.components.modals import bulk_import_dialog

        self._import_preview = preview

        def on_add(_e=None) -> None:
            if self._import_preview is not None:
                confirm_add(
                    self._import_preview,
                    self.repo,
                    format_preference=self._default_format(),
                    upscale=self._default_upscale(),
                )
                self._import_preview = None
            self.close_dialog()
            self.refresh_queue(force=True)

        self.bulk_dialog = bulk_import_dialog(
            new_count,
            dup_count,
            on_add=on_add,
            on_cancel=self.close_dialog,
        )
        return self.dialogs.open("bulk", self.bulk_dialog)

    def open_playlist_modal(self, title: str, entries: list[Any]) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import playlist_dialog

        self.playlist_entries = list(entries)
        self.playlist_selected = set(range(len(entries)))

        def on_enqueue(_e=None) -> None:
            self.playlist_enqueued = sorted(self.playlist_selected)
            self.close_dialog()

        self.playlist_dialog = playlist_dialog(
            title,
            entries,
            on_enqueue=on_enqueue,
            on_cancel=self.close_dialog,
            on_select_all=lambda: setattr(self, "playlist_selected", set(range(len(entries)))),
            on_select_none=lambda: setattr(self, "playlist_selected", set()),
        )
        return self.dialogs.open("playlist", self.playlist_dialog)

    def open_quit_busy(self) -> ft.AlertDialog:
        from frameforge.gui.exit_policy import OUTCOME_EXIT, apply_quit_choice
        from frameforge.ui_flet.components.modals import quit_busy_dialog

        self.quit_choice: str | None = None

        def choose(c: str) -> None:
            self.quit_choice = c
            self.close_dialog()
            outcome = apply_quit_choice(self.worker, c)
            if outcome == OUTCOME_EXIT:
                self._finish_exit()

        self.quit_dialog = quit_busy_dialog(on_choice=choose, on_cancel=self.close_dialog)
        return self.dialogs.open("quit", self.quit_dialog)

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

    def _ensure_file_picker(self) -> ft.FilePicker:
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        page = self.page
        if page is not None:
            services = getattr(page, "services", None)
            if services is None:
                page.services = []
                services = page.services
            if self.file_picker not in services:
                services.append(self.file_picker)
                try:
                    page.update()
                except Exception:  # noqa: BLE001
                    pass
        return self.file_picker

    def import_file(self, path: str | None = None) -> ft.AlertDialog | None:
        """Hero Import: picker (or explicit path) → confirm modal → pending only. Never arms."""
        if path:
            return self.show_import_preview(path)
        if self.page is None:
            self._pending_import = True
            return None
        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            runner(self._pick_import_file)
        return None

    async def _pick_import_file(self) -> None:
        picker = self._ensure_file_picker()
        files = await picker.pick_files(
            dialog_title="Import URL list",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt", "md"],
        )
        if not files:
            return
        picked = files[0].path
        if picked:
            self.show_import_preview(picked)

    def show_import_preview(self, path: str | Path) -> ft.AlertDialog:
        from frameforge.download.bulk_import import preview_import

        preview = preview_import(path, self.repo)
        return self.open_bulk_confirm(preview.new_count, preview.skipped_dupe_count, preview=preview)

    def confirm_bulk_import(self) -> None:
        data = getattr(getattr(self, "bulk_dialog", None), "data", None) or {}
        on_add = data.get("on_add")
        if on_add:
            on_add()

    def import_cookies_from_browser_for_site(self, url_or_domain: str, *, browser: str = "firefox"):
        if self.import_browser_fn is not None:
            return self.import_browser_fn(url_or_domain, browser=browser)
        from frameforge.download.browser_import import import_cookies_from_browser

        return import_cookies_from_browser(
            url_or_domain,
            browser=browser,
            runner=self._browser_cookie_runner,
        )

    def import_cookies_txt_path(self, path: str | Path) -> None:
        from frameforge.download import cookies as cookie_mod

        raw = self._auth_domain_value()
        err = self._auth_error_control()
        try:
            domain = cookie_mod.normalize_domain(raw)
            dest = cookie_mod.import_netscape_cookies(domain, Path(path))
        except Exception as exc:  # noqa: BLE001
            if err is not None:
                err.value = str(exc)
                err.visible = True
                if self.page is not None:
                    self.page.update()
            return
        if err is not None:
            err.value = f"Saved cookies to {dest}"
            err.visible = True
        self.close_dialog()

    def _auth_domain_value(self) -> str:
        dlg = getattr(self, "auth_dialog", None)
        data = getattr(dlg, "data", None) or {}
        field = data.get("field")
        return (getattr(field, "value", None) or "").strip()

    def _auth_error_control(self) -> Any | None:
        dlg = getattr(self, "auth_dialog", None)
        data = getattr(dlg, "data", None) or {}
        return data.get("error")

    def _set_auth_error(self, text: str) -> None:
        err = self._auth_error_control()
        if err is None:
            return
        err.value = text
        err.visible = bool(text)
        if self.page is not None:
            self.page.update()

    def _auth_firefox(self, _e: Any = None) -> None:
        raw = self._auth_domain_value()
        if not raw:
            self._set_auth_error("Enter a site URL or domain first.")
            return
        result = self.import_cookies_from_browser_for_site(raw, browser="firefox")
        if getattr(result, "ok", False):
            self.close_dialog()
            return
        self._set_auth_error(getattr(result, "message", None) or "Firefox import failed.")

    def _auth_choose_txt(self, _e: Any = None) -> None:
        if self.page is None:
            return
        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            runner(self._pick_cookies_txt)

    async def _pick_cookies_txt(self) -> None:
        picker = self._ensure_file_picker()
        files = await picker.pick_files(
            dialog_title="Import Netscape cookies.txt",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"],
        )
        if not files or not files[0].path:
            return
        self.import_cookies_txt_path(files[0].path)

    def open_authenticate(self, prefill: str | None = None) -> ft.AlertDialog:
        from frameforge.ui_flet.components.modals import authenticate_dialog

        if self.dialogs.kind == "auth" and self.dialogs.current is not None:
            return self.dialogs.open("auth", self.dialogs.current)
        host = ""
        if prefill:
            host = urlparse(prefill).hostname or prefill
        self.auth_dialog = authenticate_dialog(
            host or "site",
            prefill=prefill or "",
            on_firefox=self._auth_firefox,
            on_txt=self._auth_choose_txt,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("auth", self.auth_dialog)

    def open_settings(self) -> ft.AlertDialog:
        if self.dialogs.kind == "settings" and self.dialogs.current is not None:
            return self.dialogs.open("settings", self.dialogs.current)
        if self.bridge.settings_open and self.settings_dialog is not None:
            return self.dialogs.open("settings", self.settings_dialog)

        self.settings_dialog = build_settings_dialog(
            self.repo,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("settings", self.settings_dialog)

    def _on_keyboard(self, e: Any) -> None:
        key = getattr(e, "key", None)
        if key in {"Escape", "Esc"}:
            self.close_dialog()

    def _on_window_event(self, e: Any) -> None:
        et = getattr(e, "type", None)
        name = getattr(et, "value", et)
        if name in ("close", getattr(ft.WindowEventType, "CLOSE", "close")):
            self.handle_window_close()

    def _on_disconnect(self, _e: Any = None) -> None:
        if not self._shutdown_complete:
            self._finish_exit()

    def handle_window_close(self, _e: Any = None) -> str:
        from frameforge.gui.exit_policy import NEEDS_CHOICE, classify_exit

        kind = classify_exit(self.repo, self.worker)
        if kind == NEEDS_CHOICE:
            self.open_quit_busy()
            return "choice"
        self._finish_exit()
        return "exit"

    def _finish_exit(self) -> None:
        if self._shutdown_complete:
            return
        self.close_dialog()
        self.shutdown()
        self._shutdown_complete = True
        if self.exit_process_on_quit:
            self._destroy_and_exit()

    def _destroy_and_exit(self) -> None:
        page = self.page
        if page is not None:
            win = getattr(page, "window", None)
            if win is not None:
                try:
                    win.prevent_close = False
                except Exception:  # noqa: BLE001
                    pass
                for meth in ("destroy", "close"):
                    fn = getattr(win, meth, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:  # noqa: BLE001
                            pass
                        break
        os._exit(0)

    def attach_page(self, page: ft.Page) -> None:
        self.page = page
        self.exit_process_on_quit = isinstance(page, ft.Page)
        apply_page_chrome(page)
        win = getattr(page, "window", None)
        if win is not None:
            win.prevent_close = True
            win.on_event = self._on_window_event
        page.on_disconnect = self._on_disconnect
        page.on_keyboard_event = self._on_keyboard
        page.on_close = self.handle_window_close
        self._ensure_file_picker()
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
    global _GUI_RUNNING
    if _GUI_RUNNING:
        raise RuntimeError("FrameForge GUI is already running in this process")
    _GUI_RUNNING = True
    ui = create_ui(**kwargs)

    def _main(page: ft.Page) -> None:
        ui.attach_page(page)

    try:
        ft.app(_main)
    finally:
        _GUI_RUNNING = False
        if not ui._shutdown_complete:
            ui.shutdown()
