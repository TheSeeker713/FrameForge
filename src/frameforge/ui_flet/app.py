"""Flet desktop shell — light FrameForge window."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.library.store import LibraryStore
from frameforge.paths import db_path, ensure_output_tree
from frameforge.pipeline import build_worker
from frameforge.ui_flet.bridge import UiBridge
from frameforge.ui_flet.components.job_card import (
    build_floating_bar,
    build_job_card,
    build_queue_chrome,
    empty_queue_state,
)
from frameforge.ui_flet.components.library import (
    add_to_collection_dialog,
    build_library_toolbar,
    confirm_remove_dialog,
    confirm_reset_library_dialog,
    repair_summary_dialog,
    create_collection_dialog,
    duplicate_report_dialog,
    empty_library_state,
    junk_triage_dialog,
    library_tile,
    new_downloads_dialog,
    onboarding_dialog,
    private_disposition_dialog,
    private_password_dialog,
    send_private_dialog,
)
from frameforge.ui_flet.components.settings_dialog import build_settings_dialog
from frameforge.ui_flet.components.status_pill import status_from_repo
from frameforge.ui_flet.dialog_host import DialogHost
from frameforge.ui_flet.job_view import floating_bar_view, structural_sig
from frameforge.ui_flet.queue_chrome import queue_chrome_spec
from frameforge.ui_flet.elevation import elevated_filled_button, elevated_outlined_button
from frameforge.ui_flet.theme import COLORS, TAB_LABELS
from frameforge.ui_flet.window_chrome import USE_CUSTOM_TITLE_BAR, apply_page_chrome, build_custom_title_bar

log = logging.getLogger(__name__)

_GUI_RUNNING = False
SHUTDOWN_WATCHDOG_SEC = 3.0
QUIT_HARD_EXIT_DELAY_SEC = 0.35
LIBRARY_MOVE_JOIN_SEC = 2.5
CLOSE_DEBOUNCE_SEC = 0.25


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
    show_pause: bool = False,
    show_stop: bool = False,
    on_pause: Any | None = None,
    on_stop: Any | None = None,
) -> ft.Row:
    status_ctrl = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=999,
        content=ft.Text(status_text, color=COLORS["text_secondary"], size=13),
        data={"kind": "status"},
    )
    pause_btn = elevated_outlined_button("Pause", on_click=lambda _e: on_pause and on_pause())
    pause_btn.visible = show_pause
    stop_btn = elevated_outlined_button("Stop", on_click=lambda _e: on_stop and on_stop())
    stop_btn.visible = show_stop
    row = ft.Row(
        [
            ft.Text(
                "FrameForge",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=COLORS["text_primary"],
            ),
            ft.Container(expand=True),
            status_ctrl,
            ft.Container(expand=True),
            pause_btn,
            stop_btn,
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
    row.data = {"status": status_ctrl, "pause": pause_btn, "stop": stop_btn}
    return row


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
    library: ft.Control | None = None,
    thumbs: ft.Control | None = None,
) -> ft.Tabs:
    views = [
        queue or _placeholder_panel("Queue"),
        history or _placeholder_panel("History"),
        library or thumbs or _placeholder_panel("Library"),
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
        self.library = LibraryStore(self.repo)
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
        self.title_bar: ft.Control | None = None
        self.hero: ft.Row | None = None
        self.tabs: ft.Tabs | None = None
        self.selected_ids: set[int] = set()
        self.expanded_failed: set[int] = set()
        self.queue_list: ft.ListView | None = None
        self.queue_chrome: ft.Container | None = None
        self.history_list: ft.ListView | None = None
        self.library_grid: ft.GridView | None = None
        self.library_grid_host: ft.Container | None = None
        self.library_stack: ft.Stack | None = None
        self.library_empty: ft.Container | None = None
        self.library_toolbar: ft.Control | None = None
        self.library_body: ft.Column | None = None
        self.thumbs_grid: ft.GridView | None = None
        self.library_visible_count: int = 0
        self.library_selected_ids: set[int] = set()
        self.library_search: str = ""
        self.library_sort: str = "date"
        self.library_filter_source: str | None = None
        self.library_filter_collection_id: int | None = None
        self.library_filter_flag: str | None = None
        self._library_prompt_deferred = False
        self._library_move_progress: tuple[int, int] | None = None
        self._library_onboard_error: str | None = None
        self._library_mover: Any | None = None
        self._library_moving = False
        self._library_move_summary: str | None = None
        self._library_move_hook: Any | None = None
        self._library_scan_roots: list[Path] | None = None
        self._tree_repair_thread: threading.Thread | None = None
        self._repair_busy = False
        self._repair_status: ft.Text | None = None
        self._repair_button: Any | None = None
        self._move_status: ft.Text | None = None
        self._move_file: ft.Text | None = None
        self._move_bar: ft.ProgressBar | None = None
        self._move_progress_column: ft.Column | None = None
        self.private_session_password: str | None = None
        self._pending_private_packs: list[Any] = []
        self.floating: ft.Container | None = None
        self.resource_banner: ft.Container | None = None
        self.undo_banner: ft.Container | None = None
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
        self._exiting = False
        self._close_clicks = 0
        self._last_close_event = 0.0
        self._watchdog_armed = False
        self._watchdog_seconds = SHUTDOWN_WATCHDOG_SEC
        self._import_preview: Any | None = None
        self._pending_import = False
        self._browser_cookie_runner: Any | None = None
        self.import_browser_fn: Any | None = None
        self.last_more_action: str | None = None
        self.more_invocations: list[str] = []
        self._activity_note: str | None = None
        self._idle_reason: str | None = None
        self._action_lock = False
        self.last_chrome: dict[str, Any] | None = None
        self.last_copied_report: str | None = None
        self.last_clipboard_status: str | None = None
        self.last_destroy_status: str | None = None
        self.last_toast: str | None = None
        self.bridge.set_fail_pause_handler(self._on_fail_pause)

    def close_dialog(self, _e: Any = None) -> None:
        self.dialogs.close(_e)

    def _on_fail_pause(self, job: Any, payload: dict[str, Any]) -> None:
        self.fail_pause_payload = payload
        self.fail_pause_shown += 1
        pending = self.repo.count_by_status("pending")
        self._idle_reason = "fail_pause"
        self._activity_note = (
            f"Idle • {pending} ready — queue paused after failure" if pending else "Queue paused after failure"
        )
        if self.page is not None:
            self.dialogs.open("fail_pause", self._fail_pause_dialog(payload))

    def _fail_pause_dialog(self, payload: dict[str, Any]) -> ft.AlertDialog:
        jid = int(payload["job_id"])
        status = ft.Text("", color=COLORS["warn"], visible=False)

        def retry_resume(_e=None) -> None:
            self.bridge.handle_fail_pause_action("retry_resume", jid)
            self.close_dialog()
            self.refresh_queue()

        resume_btn = elevated_filled_button("Retry this job and resume queue", on_click=retry_resume)
        resume_btn.visible = False
        cat = str(payload.get("category") or "")
        js_runtime = cat == "js_runtime"
        output_missing = cat == "output_missing"
        hide_auth = js_runtime or output_missing
        browser_pick = ft.Dropdown(
            label="Browser (Firefox preferred — Chrome App-Bound Encryption often fails)",
            value="firefox",
            options=[
                ft.dropdown.Option("firefox", text="Firefox (recommended)"),
                ft.dropdown.Option("edge", text="Edge"),
                ft.dropdown.Option("chrome", text="Chrome (often blocked by DPAPI)"),
            ],
            width=360,
            visible=not hide_auth,
        )

        def act(aid: str):
            def _(_e=None):
                if aid == "authenticate":
                    url = payload.get("url")
                    self.open_authenticate(prefill=url)
                    return
                if aid == "import_browser":
                    url = str(payload.get("url") or "")
                    chosen = (browser_pick.value or "firefox").strip().lower()
                    recovered = self.bridge.recover_bot_cookies(
                        url,
                        import_browser=lambda u, b=chosen: self.import_cookies_from_browser_for_site(
                            u, browser=b
                        ),
                        probe=getattr(self, "cookie_probe", None),
                    )
                    status.value = str(recovered.get("message") or "")
                    status.visible = True
                    status.color = COLORS["success"] if recovered.get("ok") else COLORS["danger"]
                    resume_btn.visible = bool(recovered.get("ok"))
                    if self.page is not None:
                        self.page.update()
                    return
                if aid == "open_folder":
                    self._open_fail_pause_folder(jid)
                    return
                self.bridge.handle_fail_pause_action(aid, jid)
                self.close_dialog()
                self.refresh_queue()

            return _

        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Text("Queue paused"),
            content=ft.Column(
                [
                    ft.Text(str(payload.get("title") or "")),
                    ft.Text(str(payload.get("url") or ""), color=COLORS["text_secondary"]),
                    ft.Text(f"Cause: {payload.get('cause') or ''}", color=COLORS["warn"]),
                    ft.Text(
                        "YouTube n-challenge failed: install Deno + yt-dlp-ejs and restart FrameForge. "
                        "This is not a cookie/login problem."
                        if js_runtime
                        else (
                            "The file is missing on disk. Retry (force if the archive is stale), "
                            "open the folder, or skip this job. This is not a cookie/login problem."
                            if output_missing
                            else "Prefer Firefox import or a Netscape cookies.txt. Chrome App-Bound Encryption "
                            "cannot be fixed by FrameForge. Import cookies, then retry only after they validate."
                        ),
                        color=COLORS["text_secondary"],
                        size=12,
                    ),
                    browser_pick,
                    status,
                    resume_btn,
                ],
                spacing=8,
                width=460,
            ),
            actions=[
                elevated_outlined_button("Copy full report", on_click=self._copy_fail_pause_report),
                *(
                    []
                    if hide_auth
                    else [
                        elevated_filled_button("Import from Firefox / browser", on_click=act("import_browser")),
                        elevated_outlined_button("Import cookies.txt", on_click=act("authenticate")),
                    ]
                ),
                elevated_outlined_button(
                    "Force re-download" if payload.get("archive_hit") and output_missing else "Retry this job",
                    on_click=act("retry"),
                ),
                *(
                    [elevated_outlined_button("Open folder", on_click=act("open_folder"))]
                    if output_missing
                    else []
                ),
                elevated_outlined_button("Skip & resume queue", on_click=act("skip_resume")),
                elevated_outlined_button("Stop queue", on_click=act("stop")),
            ],
        )
        dlg.data = {"status": status, "resume": resume_btn, "browser": browser_pick, "payload": payload}
        return dlg

    def copy_error_report(
        self,
        job: Any | None = None,
        *,
        payload: dict[str, Any] | None = None,
        extra_error: str | None = None,
    ) -> str:
        from frameforge.error_report import format_full_error_report

        if job is None and payload and payload.get("job_id") is not None:
            try:
                job = self.repo.get(int(payload["job_id"]))
            except Exception:  # noqa: BLE001
                job = None
        text = format_full_error_report(job, payload=payload, extra_error=extra_error)
        self.last_copied_report = text
        page = self.page
        if page is not None:
            from frameforge.ui_flet.clipboard import request_set_clipboard

            self.last_clipboard_status = request_set_clipboard(page, text)
        return text

    def _copy_fail_pause_report(self, _e: Any = None) -> str:
        return self.copy_error_report(payload=self.fail_pause_payload)

    def _copy_auth_error(self, _e: Any = None) -> str:
        err = self._auth_error_control()
        extra = getattr(err, "value", None) or ""
        return self.copy_error_report(extra_error=extra or "Authenticate dialog", payload={"url": self._auth_domain_value()})

    def copy_job_error(self, job_id: int) -> str:
        job = self.repo.get(int(job_id))
        return self.copy_error_report(job)

    def build(self) -> ft.Column:
        status = status_from_repo(self.repo, self.worker)
        self.header = build_header(
            status_text=status,
            on_settings=lambda _e=None: self.open_settings(),
            on_authenticate=lambda _e=None: self.open_authenticate(),
            on_pause=self.pause_active,
            on_stop=self.stop_active,
        )
        self.hero = build_hero(
            on_add=lambda _e=None: self.add_url(),
            on_import=lambda _e=None: self.import_file(),
        )
        self.resource_banner = ft.Container(visible=False, data={"text": ""})
        self.undo_banner = ft.Container(visible=False, data={"text": ""})
        self.queue_chrome = ft.Container(visible=False)
        self.queue_list = ft.ListView(expand=True, spacing=8, padding=4)
        self.history_list = ft.ListView(expand=True, spacing=8, padding=4)
        self.library_grid = ft.GridView(
            expand=True,
            runs_count=4,
            max_extent=220,
            child_aspect_ratio=0.72,
            spacing=8,
            run_spacing=8,
            padding=8,
            build_controls_on_demand=False,
        )
        self.thumbs_grid = self.library_grid
        self.library_grid_host = ft.Container(expand=True, content=self.library_grid)
        self.library_empty = ft.Container(visible=False, expand=True)
        self.library_stack = ft.Stack(
            [self.library_grid_host, self.library_empty],
            expand=True,
            fit=ft.StackFit.EXPAND,
        )
        self.library_toolbar = ft.Container()
        self.library_body = ft.Column(
            [self.library_toolbar, self.library_stack],
            expand=True,
            spacing=8,
        )
        self.floating = ft.Container(visible=False)
        queue_body = ft.Column(
            [self.queue_chrome, self.floating, self.queue_list],
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
        self.tabs = build_tabs(queue_body, history_body, self.library_body)
        self.tabs.on_change = self._on_tabs_change
        controls: list[ft.Control] = [
            self.header,
            self.hero,
            self.undo_banner,
            self.resource_banner,
            self.tabs,
        ]
        if USE_CUSTOM_TITLE_BAR:
            self.title_bar = build_custom_title_bar(
                on_close=self.handle_window_close,
                on_min=self.minimize_window,
                on_max=self.toggle_maximize,
                on_drag_start=self._on_title_drag_start,
                on_drag_end=self._on_title_drag_end,
            )
            controls.insert(0, self.title_bar)
        else:
            self.title_bar = None
        root = ft.Column(
            expand=True,
            spacing=16,
            controls=controls,
        )
        self.refresh_queue(force=True)
        self.refresh_history()
        self.refresh_library()
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
        spec = queue_chrome_spec(
            self.queue_jobs(),
            self.selected_ids,
            undo_available=bool(self.bridge.clear_undo),
            armed=bool(getattr(self.worker, "is_armed", False)),
        )
        if self.queue_chrome is None:
            return
        built = build_queue_chrome(
            spec,
            on_download_all=self.download_all_pending,
            on_retry_failed=self.retry_all_failed,
            on_clear_finished=self.clear_finished,
            on_clear_selected=self.clear_selected,
            on_undo=self.undo_clear,
            on_pause=self.pause_active,
            on_stop=self.stop_active,
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
        from frameforge.download.thumbnails import backfill_missing_thumbnails

        try:
            backfill_missing_thumbnails(self.repo, extract_still=False)
        except Exception:  # noqa: BLE001
            pass
        jobs = self.queue_jobs()
        armed = bool(getattr(self.worker, "is_armed", False))
        sig = (structural_sig(jobs), armed, self._activity_note)
        active = next((j for j in jobs if j.status in {"downloading", "upscaling", "converting"}), None)
        waiting = None
        if armed and active is None:
            waiting = next((j for j in jobs if j.status == "pending"), None)
        if not force and sig == self._queue_sig and self.queue_list is not None:
            if active is not None:
                self.update_active_progress(active)
            self._sync_header()
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
                    show_progress=(active is not None and job.id == active.id)
                    or (waiting is not None and job.id == waiting.id),
                    on_toggle=self.toggle_select,
                    on_retry=self.retry_failed_job,
                    on_reauth=self.reauthenticate_job,
                    on_expand=self.toggle_failed_expand,
                    on_overflow=self.handle_overflow,
                    on_copy_error=self.copy_job_error,
                    on_play=self.play_job,
                )
                for job in jobs
            ]
        self._sync_queue_chrome()
        self._sync_floating()
        self._sync_header()
        if self.page is not None:
            self.page.update()

    def update_active_progress(self, job: Any) -> None:
        if self.queue_list is None:
            return
        pct = float(getattr(job, "progress", 0) or 0)
        opts = job.options() if hasattr(job, "options") else {}
        speed = opts.get("speed_str") or ""
        eta = opts.get("eta_str") or ""
        for card in self.queue_list.controls:
            data = getattr(card, "data", None) or {}
            if data.get("job_id") != job.id:
                continue
            bar = data.get("progress_bar")
            if bar is not None:
                bar.value = None if pct <= 0 else min(1.0, max(0.0, pct / 100.0))
            label = data.get("progress_label")
            if label is not None:
                bits = [f"{int(pct)}%"] if pct > 0 else ["Starting…"]
                if speed:
                    bits.append(str(speed))
                if eta:
                    bits.append(str(eta))
                label.value = "  ".join(bits)
            view = dict(data.get("view") or {})
            view["progress"] = pct
            view["speed"] = speed
            view["eta"] = eta
            data["view"] = view
            card.data = data
            if self.page is not None:
                self.page.update()
            return

    def minimize_window(self) -> None:
        win = getattr(self.page, "window", None) if self.page is not None else None
        if win is not None:
            win.minimized = True

    def toggle_maximize(self) -> None:
        win = getattr(self.page, "window", None) if self.page is not None else None
        if win is not None:
            win.maximized = not bool(getattr(win, "maximized", False))

    def _on_title_drag_start(self, _e: Any = None) -> None:
        if self.page is not None:
            self.last_chrome = apply_page_chrome(self.page, set_size=False)

    def _on_title_drag_end(self, _e: Any = None) -> None:
        if self.page is not None:
            self.last_chrome = apply_page_chrome(self.page, set_size=False)

    def _sync_header(self) -> None:
        if self.header is None:
            return
        text = self._activity_note or status_from_repo(
            self.repo, self.worker, idle_reason=self._idle_reason
        )
        data = self.header.data or {}
        status_ctrl = data.get("status")
        if status_ctrl is not None and getattr(status_ctrl, "content", None) is not None:
            status_ctrl.content.value = text
        spec = queue_chrome_spec(
            self.queue_jobs(),
            self.selected_ids,
            armed=bool(getattr(self.worker, "is_armed", False)),
        )
        pause_btn = data.get("pause")
        stop_btn = data.get("stop")
        if pause_btn is not None:
            pause_btn.visible = bool(spec.get("show_pause"))
        if stop_btn is not None:
            stop_btn.visible = bool(spec.get("show_stop"))
        if self.page is not None:
            self.page.update()

    def pause_active(self) -> None:
        """Pause the in-flight job (or disarm if between jobs). Remaining stay pending."""
        for status in ("downloading", "upscaling", "converting"):
            jobs = list(self.repo.list_jobs(status))
            if jobs:
                self.worker.pause_job(jobs[0].id)
                self._activity_note = "Paused"
                self.refresh_queue(force=True)
                return
        self.worker.disarm()
        self._activity_note = "Queue paused"
        self.refresh_queue(force=True)

    def stop_active(self) -> None:
        """Cancel the in-flight job and disarm. Remaining stay pending."""
        self.worker.stop_run()
        pending = self.repo.count_by_status("pending")
        self._idle_reason = "stopped"
        self._activity_note = f"Idle • {pending} ready — stopped" if pending else "Stopped"
        self.refresh_queue(force=True)

    def tick(self) -> None:
        """Poll SQLite into the cards. Tests call this; the live window schedules it."""
        if self._exiting or self._shutdown_complete:
            return
        if getattr(self.dialogs, "kind", None) == "quit":
            return
        active = next(
            (j for j in self.queue_jobs() if j.status in {"downloading", "upscaling", "converting"}),
            None,
        )
        if active is not None:
            self._activity_note = None
            self._idle_reason = None
        self.refresh_queue()
        self._sync_header()
        if self.page is not None:
            self.last_chrome = apply_page_chrome(self.page, set_size=False)

    def _schedule_tick(self) -> None:
        if self._exiting or self._shutdown_complete or not self.exit_process_on_quit:
            return

        def _arm_next() -> None:
            if self._exiting or self._shutdown_complete:
                return
            active = False
            try:
                active = any(
                    j.status in {"downloading", "upscaling", "converting"} for j in self.queue_jobs()
                )
            except Exception:  # noqa: BLE001
                pass
            delay = 0.5 if (active or getattr(self.worker, "is_armed", False)) else 1.5
            timer = threading.Timer(delay, self._schedule_tick)
            timer.daemon = True
            timer.start()

        def _run() -> None:
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                pass
            _arm_next()

        runner = getattr(self.page, "run_task", None) if self.page is not None else None
        if callable(runner):
            async def _on_loop() -> None:
                _run()

            try:
                runner(_on_loop)
                return
            except Exception:  # noqa: BLE001
                pass
        _run()

    def toggle_failed_expand(self, job_id: int) -> None:
        if job_id in self.expanded_failed:
            self.expanded_failed.discard(job_id)
        else:
            self.expanded_failed.add(job_id)
        self.refresh_queue(force=True)

    def play_job(self, job_id: int) -> None:
        from frameforge.util.reveal import RevealError, open_in_default_player, resolve_job_media_path

        try:
            path = resolve_job_media_path(self.repo.get(job_id))
            open_in_default_player(path, launch=self.reveal_launch)
        except RevealError:
            self._show_toast("File not found — cannot play")

    def retry_failed_job(self, job_id: int) -> None:
        self.bridge.queue_again([job_id])
        self._idle_reason = None
        self._activity_note = "Queued — press Download selected or Download all pending"
        self.refresh_queue(force=True)

    def retry_all_failed(self) -> list[int]:
        ids = self.bridge.retry_failed_ids(
            [j.id for j in self.repo.list_jobs("failed")]
            + [j.id for j in self.repo.list_jobs("cancelled")],
            arm=False,
        )
        self._idle_reason = None
        self._activity_note = (
            "Queued — press Download selected or Download all pending"
            if ids
            else "No cancelled or failed jobs to resume."
        )
        self.refresh_queue(force=True)
        return ids

    def retry_selected_failed(self) -> list[int]:
        if self._action_lock:
            return []
        self._action_lock = True
        try:
            ids = self.bridge.retry_failed_ids(sorted(self.selected_ids), arm=False)
            self._idle_reason = None
            self._activity_note = (
                "Queued — press Download selected or Download all pending"
                if ids
                else "Nothing to resume in the selection."
            )
            self.refresh_queue(force=True)
            return ids
        finally:
            self._action_lock = False

    def download_all_pending(self) -> None:
        if self._action_lock:
            return
        self._action_lock = True
        try:
            pending_n = self.repo.count_by_status("pending")
            if pending_n <= 0:
                self._activity_note = "No pending jobs to download."
                self.refresh_queue(force=True)
                return
            self._idle_reason = None
            self._activity_note = f"Starting {pending_n} pending download(s)…"
            self.bridge.download_all_pending()
            if not self.worker.is_armed:
                self._activity_note = "Download all did not start — worker is not armed."
            self.refresh_queue(force=True)
        finally:
            self._action_lock = False

    def clear_finished(self) -> None:
        self.bridge.clear_finished()
        self.selected_ids.clear()
        self._sync_undo_banner()
        self.refresh_queue(force=True)

    def clear_selected(self) -> None:
        if not self.selected_ids:
            return
        self.bridge.clear_selected(sorted(self.selected_ids))
        self.selected_ids.clear()
        self._sync_undo_banner()
        self.refresh_queue(force=True)

    def undo_clear(self) -> int:
        n = self.bridge.undo_clear()
        self._sync_undo_banner()
        self.refresh_queue(force=True)
        self.refresh_history()
        return n

    def _sync_undo_banner(self) -> None:
        if self.undo_banner is None:
            return
        msg = self.bridge.last_clear_message
        self.undo_banner.visible = bool(msg)
        self.undo_banner.data = {"text": msg or ""}
        if msg:
            self.undo_banner.content = ft.Row(
                [
                    ft.Text(msg, color=COLORS["text_primary"], expand=True),
                    elevated_filled_button("Undo", on_click=lambda _e: self.undo_clear()),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            self.undo_banner.content = None
        if self.page is not None:
            self.page.update()

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

    def _show_toast(self, message: str) -> None:
        self.last_toast = message
        page = self.page
        if page is None:
            return
        try:
            import flet as ft

            bar = ft.SnackBar(content=ft.Text(message), open=True)
            opener = getattr(page, "open", None)
            if callable(opener):
                opener(bar)
            else:
                page.snack_bar = bar
                page.update()
        except Exception:  # noqa: BLE001
            pass

    def _open_fail_pause_folder(self, job_id: int) -> None:
        from pathlib import Path

        from frameforge.util.reveal import RevealError, open_folder, open_job_folder

        job = self.repo.get(job_id)
        dest = job.options().get("download_output_dir")
        try:
            if dest and Path(dest).is_dir():
                open_folder(Path(dest), launch=self.reveal_launch)
                return
            open_job_folder(job, launch=self.reveal_launch)
        except RevealError:
            self._show_toast("Download folder not found")

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

    def open_cookies_folder(self, _e=None) -> None:
        from frameforge.download.cookies import open_cookies_folder as _open

        _open(launch=self.reveal_launch)

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
                on_play=self.play_job,
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
            self.bridge.clear_history_ids(sorted(self.selected_ids))
            self._sync_undo_banner()
        self.refresh_history()

    def refresh_thumbs(self) -> None:
        self.refresh_library()

    def _pending_library_jobs(self):
        from frameforge.library.ingest import completed_jobs_not_in_library

        if self.library.root() is None:
            return []
        return completed_jobs_not_in_library(self.repo, self.library)

    def _migrate_disk_roots(self) -> list[Path]:
        if self._library_scan_roots is not None:
            return list(self._library_scan_roots)
        page = self.page
        if page is None or page.__class__.__name__ == "FakePage":
            return []
        from frameforge.paths import frameforge_root

        return [frameforge_root()]

    def _pending_disk_videos(self):
        from frameforge.library.scan import download_videos_not_in_library

        if self.library.root() is None:
            return []
        return download_videos_not_in_library(self.library, roots=self._migrate_disk_roots())

    def refresh_library(self) -> None:
        if self.library_grid is None:
            return
        from frameforge.library.scan import list_playable_items, orphan_videos

        try:
            items = list_playable_items(
                self.library,
                search=self.library_search or None,
                source=self.library_filter_source,
                collection_id=self.library_filter_collection_id,
                flag=self.library_filter_flag,
                sort=self.library_sort,
            )
        except Exception:
            log.exception("Failed to load library items")
            items = []
        try:
            orphans = orphan_videos(self.library) if self.library.root() else []
        except Exception:
            log.exception("Failed to scan library folder for orphans")
            orphans = []
        pending = len(self._pending_library_jobs()) + len(self._pending_disk_videos()) if self.library.is_onboarded() else 0
        if self.library_toolbar is not None:
            toolbar = build_library_toolbar(
                count=len(items),
                search=self.library_search,
                sort=self.library_sort,
                source=self.library_filter_source,
                flag=self.library_filter_flag,
                on_search=self.set_library_search,
                on_sort=self.set_library_sort,
                on_source=self.set_library_source,
                on_flag=self.set_library_flag,
                on_new_collection=self.open_new_collection,
                on_add_collection=self.open_add_to_collection,
                on_move_new=self.open_library_new_files,
                pending_new=pending,
                has_selection=bool(self.library_selected_ids),
                on_bulk_upscale=self.upscale_library_selected,
                on_bulk_remove=lambda: self.confirm_library_remove(delete_files=False),
                on_bulk_delete=lambda: self.confirm_library_remove(delete_files=True),
                on_send_private=self.open_send_private,
                on_scan=self.scan_library_folder,
                orphan_count=len(orphans),
                on_dedupe=self.open_library_dedupe,
                on_junk=self.open_library_junk,
            )
            if self.library_body is not None and self.library_body.controls:
                self.library_body.controls[0] = toolbar
            self.library_toolbar = toolbar
        cells: list[Any] = []
        for item in items:
            try:
                cells.append(
                    library_tile(
                        item,
                        selected=item.id in self.library_selected_ids,
                        on_play=self.play_library_item,
                        on_reveal=self.reveal_library_item,
                        on_upscale=self.upscale_library_item,
                        on_toggle=self.toggle_library_selected,
                        on_favorite=self.toggle_library_favorite,
                        on_watch_later=self.toggle_library_watch_later,
                    )
                )
            except Exception:
                log.exception("Library tile failed for item %s (%s)", item.id, item.path)
        self.library_grid.controls = cells
        self.library_visible_count = len(cells)
        show_empty = len(cells) == 0
        if self.library_empty is not None:
            state = empty_library_state(
                onboarded=self.library.is_onboarded(),
                on_setup=self.on_library_opened,
                on_import=self.import_completed_downloads,
                on_scan=self.scan_library_folder,
                pending_count=pending,
                orphan_count=len(orphans),
            )
            self.library_empty.visible = show_empty
            self.library_empty.expand = show_empty
            self.library_empty.content = state.content
            self.library_empty.data = state.data
        if self.library_grid_host is not None:
            self.library_grid_host.visible = not show_empty
        if self.library_grid is not None:
            self.library_grid.visible = not show_empty
        if self.page is not None:
            try:
                self.page.update()
            except Exception:
                log.exception("page.update failed after library refresh")

    def _on_tabs_change(self, e: Any = None) -> None:
        idx = getattr(self.tabs, "selected_index", None) if self.tabs is not None else None
        if e is not None:
            ctrl = getattr(e, "control", None)
            idx = getattr(ctrl, "selected_index", idx)
        if idx == 2:
            self.on_library_opened()

    def on_library_opened(self, _e: Any = None) -> ft.AlertDialog | None:
        self.refresh_library()
        if not self.library.is_onboarded():
            return self.open_library_onboarding()
        pending_jobs = self._pending_library_jobs()
        pending_disk = self._pending_disk_videos()
        if (pending_jobs or pending_disk) and not self._library_prompt_deferred:
            return self.open_library_new_files()
        return None

    def open_library_onboarding(self) -> ft.AlertDialog:
        root = self.library.root()
        pending_jobs = self._pending_library_jobs() if root else []
        pending_disk = self._pending_disk_videos() if root else []
        pending = [*pending_jobs, *pending_disk]
        sample = [str(j.title or j.url or f"#{j.id}") for j in pending_jobs[:8]]
        if len(sample) < 8:
            sample.extend(p.name for p in pending_disk[: 8 - len(sample)])
        dlg = onboarding_dialog(
            step="move" if root else "pick",
            root_label=str(root) if root else None,
            pending_count=len(pending),
            sample_titles=sample,
            on_choose=self.pick_library_root,
            on_move=self.confirm_library_move,
            on_skip=self.skip_library_onboarding,
            on_close=self.dismiss_library_move_summary,
            progress=self._library_move_progress if isinstance(self._library_move_progress, tuple) else None,
            error=self._library_onboard_error,
            moving=self._library_moving,
            on_cancel=self.cancel_library_move,
            progress_column=self._ensure_move_progress_column(),
            summary=self._library_move_summary,
        )
        return self.dialogs.open("library_onboard", dlg, replace=True)

    def _ensure_move_progress_column(self) -> ft.Column:
        if self._move_progress_column is None:
            self._move_status = ft.Text("Moving 0 of 0…", size=13, color=COLORS["text_primary"])
            self._move_file = ft.Text("", size=12, color=COLORS["text_secondary"], max_lines=1)
            self._move_bar = ft.ProgressBar(value=0, width=420)
            self._move_progress_column = ft.Column(
                [self._move_status, self._move_file, self._move_bar],
                spacing=6,
                visible=False,
            )
        self._move_progress_column.visible = bool(self._library_moving) or bool(self._library_move_summary)
        return self._move_progress_column

    def _marshal_ui(self, fn: Any) -> None:
        if self._exiting or self._shutdown_complete:
            return

        def _safe() -> None:
            try:
                fn()
            except Exception:  # noqa: BLE001 — never kill the library-move worker
                log.exception("UI marshal callback failed")

        page = self.page
        if page is None:
            _safe()
            return
        if page.__class__.__name__ == "FakePage":
            _safe()
            return
        runner = getattr(page, "run_task", None)
        if callable(runner):
            async def _on_loop() -> None:
                _safe()

            try:
                runner(_on_loop)
                return
            except Exception:  # noqa: BLE001
                pass
        _safe()

    @property
    def library_move_running(self) -> bool:
        mover = self._library_mover
        return bool(self._library_moving or (mover is not None and getattr(mover, "running", False)))

    def wait_library_move(self, timeout: float = 10.0) -> bool:
        mover = self._library_mover
        if mover is None:
            return True
        return bool(mover.join(timeout))

    def cancel_library_move(self, _e: Any = None) -> None:
        mover = self._library_mover
        if mover is not None:
            mover.request_cancel()

    def _apply_move_progress(self, progress: Any) -> None:
        self._library_move_progress = (int(progress.index), int(progress.total))
        try:
            if self._move_status is not None:
                self._move_status.value = f"Moving {progress.index} of {progress.total}…"
            if self._move_file is not None:
                name = str(progress.current_name or "")
                self._move_file.value = name if len(name) <= 80 else name[:77] + "…"
            if self._move_bar is not None:
                total = int(progress.total) or 1
                self._move_bar.value = min(1.0, max(0.0, int(progress.index) / total))
            if self._move_progress_column is not None:
                self._move_progress_column.visible = True
        except Exception:  # noqa: BLE001 — disposed Flet controls must not abort the batch
            log.exception("Library move progress widgets failed")
        page = self.page
        if page is not None:
            try:
                page.update()
            except Exception:  # noqa: BLE001
                pass

    def _on_library_move_done(self, report: Any) -> None:
        self._library_moving = False
        if self._exiting or self._shutdown_complete:
            return
        if self._move_status is not None:
            total = int(report.moved) + int(report.failed) + int(report.skipped)
            self._move_status.value = f"Moved {report.moved} of {total or report.moved}…"
        if self._move_bar is not None:
            self._move_bar.value = 1.0
        if self._move_progress_column is not None:
            self._move_progress_column.visible = True
        self._library_move_summary = getattr(report, "summary", None)
        finishing = not self.library.is_onboarded()
        remaining_jobs = self._pending_library_jobs() if self.library.root() else []
        remaining_disk = self._pending_disk_videos() if self.library.root() else []
        remaining = [*remaining_jobs, *remaining_disk]
        cancelled = bool(getattr(report, "cancelled", False))
        if finishing and remaining and (cancelled or report.failed):
            self._library_onboard_error = (
                None if cancelled else ("; ".join(report.errors[:3]) or f"{len(remaining)} file(s) still to move")
            )
        elif finishing and not remaining:
            self.library.mark_onboarded()
            self._library_onboard_error = None
        elif finishing and remaining and not cancelled:
            self._library_onboard_error = f"{len(remaining)} file(s) could not be moved. Retry or skip."
        self._library_prompt_deferred = False
        try:
            from frameforge.library.scan import scan_ingest_folder

            if self.library.root():
                scan_ingest_folder(self.library)
        except Exception:
            log.exception("Post-migrate library folder scan failed")
        self.refresh_library()
        self.refresh_queue(force=True)
        self.open_library_onboarding()

    def dismiss_library_move_summary(self, _e: Any = None) -> None:
        self._library_move_summary = None
        self._library_move_progress = None
        self._library_onboard_error = None
        if self._move_progress_column is not None:
            self._move_progress_column.visible = False
        self.close_dialog()
        self.refresh_library()

    def confirm_library_move(self, _e: Any = None) -> list[Any]:
        from frameforge.library.mover import LibraryMoveRunner, MoveProgress, MoveReport

        if self.library.root() is None:
            return []
        if self.library_move_running:
            return []
        from frameforge.library.ingest import purge_missing_library_items

        purge_missing_library_items(self.library)
        pending_jobs = self._pending_library_jobs()
        pending_disk = self._pending_disk_videos()
        if not pending_jobs and not pending_disk:
            if not self.library.is_onboarded():
                self.library.mark_onboarded()
            self.close_dialog()
            self.refresh_library()
            return []
        self._library_onboard_error = None
        self._library_move_summary = None
        self._library_moving = True
        total = len(pending_jobs) + len(pending_disk)
        self._ensure_move_progress_column()
        self._apply_move_progress(MoveProgress(index=0, total=total, current_name="Starting…"))
        self.open_library_onboarding()

        mover = LibraryMoveRunner(self.repo.db_path)
        mover.between_files = self._library_move_hook
        self._library_mover = mover

        def on_progress(progress: MoveProgress) -> None:
            self._marshal_ui(lambda: self._apply_move_progress(progress))

        def on_done(report: MoveReport) -> None:
            self._marshal_ui(lambda: self._on_library_move_done(report))

        mover.start(
            [j.id for j in pending_jobs],
            extra_paths=pending_disk,
            on_progress=on_progress,
            on_done=None if self.page is None else on_done,
        )
        if self.page is None:
            mover.join()
            if mover.report is not None:
                self._on_library_move_done(mover.report)
            return list(mover.report.results) if mover.report else []
        return []

    def import_completed_downloads(self, _e: Any = None) -> ft.AlertDialog | None:
        """Empty-state CTA: never leave the user stuck with no import path."""
        if not self.library.is_onboarded():
            return self.on_library_opened()
        pending = self._pending_library_jobs()
        disk = self._pending_disk_videos()
        if pending or disk:
            return self.open_library_new_files()
        self._show_toast("No completed downloads left to import")
        return None

    def open_library_new_files(self, _e: Any = None) -> ft.AlertDialog | None:
        pending = self._pending_library_jobs()
        disk = self._pending_disk_videos()
        n = len(pending) + len(disk)
        if not n:
            return None
        dlg = new_downloads_dialog(
            n,
            on_yes=self.confirm_library_move,
            on_not_now=self.defer_library_new_files,
        )
        return self.dialogs.open("library_new", dlg)

    def defer_library_new_files(self, _e: Any = None) -> None:
        self._library_prompt_deferred = True
        self.close_dialog()

    def pick_library_root(self, _e: Any = None) -> None:
        if self.page is None:
            return
        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            runner(self._pick_library_root)

    async def _pick_library_root(self) -> None:
        # Native folder picker cannot sit under a modal. Dismiss the wizard, then restore step B.
        self.close_dialog()
        picker = self._ensure_file_picker()
        getter = getattr(picker, "get_directory_path", None)
        if not callable(getter):
            if not self.library.is_onboarded():
                self.open_library_onboarding()
            return
        path = await getter(dialog_title="Choose Library folder")
        if path:
            self.apply_library_root(path)
            return
        if not self.library.is_onboarded():
            self.open_library_onboarding()

    def apply_library_root(self, path: str | Path) -> ft.AlertDialog | None:
        """Persist library_root only. Never marks onboarded — that is Move or Skip."""
        self.library.set_root(path)
        self._library_onboard_error = None
        self._library_move_progress = None
        self.refresh_library()
        if self.library.is_onboarded():
            self._show_toast("Library folder updated")
            return None
        return self.open_library_onboarding()

    def skip_library_onboarding(self, _e: Any = None) -> None:
        if self.library.root() is None:
            return
        if self.library_move_running:
            self.cancel_library_move()
            return
        self.library.mark_onboarded()
        self._library_onboard_error = None
        self._library_move_progress = None
        self._library_move_summary = None
        self.close_dialog()
        self.refresh_library()

    def set_library_search(self, value: str) -> None:
        self.library_search = value or ""
        self.refresh_library()

    def set_library_sort(self, value: str) -> None:
        self.library_sort = value or "date"
        self.refresh_library()

    def set_library_source(self, value: str | None) -> None:
        self.library_filter_source = value
        self.refresh_library()

    def set_library_flag(self, value: str | None) -> None:
        self.library_filter_flag = value
        self.refresh_library()

    def toggle_library_selected(self, item_id: int) -> None:
        if item_id in self.library_selected_ids:
            self.library_selected_ids.discard(item_id)
        else:
            self.library_selected_ids.add(item_id)
        self.refresh_library()

    def scan_library_folder(self, _e: Any = None) -> int:
        from frameforge.library.scan import scan_library_folder

        if self.library.root() is None:
            return 0
        added = scan_library_folder(self.library)
        self.refresh_library()
        if added:
            self._show_toast(f"Indexed {len(added)} video{'s' if len(added) != 1 else ''} from disk")
        else:
            self._show_toast("No new videos found on disk")
        return len(added)

    def open_library_dedupe(self, _e: Any = None) -> ft.AlertDialog | None:
        from frameforge.library.dedupe import find_duplicate_groups

        groups = find_duplicate_groups(self.library)
        if not groups:
            self._show_toast("No duplicates found")
            return None
        self._pending_dedupe_groups = groups
        dlg = duplicate_report_dialog(
            groups,
            on_merge=self.confirm_library_dedupe,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("library_dedupe", dlg)

    def confirm_library_dedupe(self, _e: Any = None) -> None:
        from frameforge.library.dedupe import merge_duplicate_groups

        groups = getattr(self, "_pending_dedupe_groups", None)
        report = merge_duplicate_groups(self.library, groups, recycle=self.reveal_launch)
        self._pending_dedupe_groups = None
        self.close_dialog()
        self.refresh_library()
        self._show_toast(report.summary)

    def _junk_scan_roots(self) -> list[Path]:
        roots: list[Path] = []
        lib = self.library.root()
        if lib is not None:
            roots.append(lib)
            if lib.parent.name.lower() == "frameforge":
                roots.append(lib.parent)
        roots.extend(self._migrate_disk_roots())
        return roots

    def open_library_junk(self, _e: Any = None) -> ft.AlertDialog | None:
        from frameforge.library.junk import find_junk

        files = find_junk(self._junk_scan_roots())
        if not files:
            self._show_toast("No junk files found")
            return None
        self._pending_junk = files
        dlg = junk_triage_dialog(
            files,
            on_recycle=self.confirm_junk_recycle,
            on_keep=self.close_dialog,
            on_move=self.pick_junk_move_folder,
        )
        return self.dialogs.open("library_junk", dlg)

    def confirm_junk_recycle(self, _e: Any = None) -> None:
        from frameforge.library.junk import recycle_junk

        files = getattr(self, "_pending_junk", None) or []
        recycle_junk([j.path for j in files], recycle=self.reveal_launch)
        self._pending_junk = None
        self.close_dialog()
        self._show_toast(f"Sent {len(files)} junk file(s) to Recycle Bin")

    def pick_junk_move_folder(self, _e: Any = None) -> None:
        if self.page is None:
            return
        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            runner(self._pick_junk_move_folder)

    async def _pick_junk_move_folder(self) -> None:
        picker = self._ensure_file_picker()
        getter = getattr(picker, "get_directory_path", None)
        if not callable(getter):
            return
        path = await getter(dialog_title="Move junk files to folder")
        if path:
            self.confirm_junk_move(path)

    def confirm_junk_move(self, dest: str | Path) -> None:
        from frameforge.library.junk import move_junk

        files = getattr(self, "_pending_junk", None) or []
        move_junk([j.path for j in files], Path(dest))
        self._pending_junk = None
        self.close_dialog()
        self._show_toast(f"Moved {len(files)} junk file(s)")

    def play_library_item(self, item_id: int) -> None:
        from frameforge.library.actions import play_library_item
        from frameforge.library.scan import heal_item
        from frameforge.util.reveal import RevealError

        try:
            item = heal_item(self.library, self.library.get(item_id))
            play_library_item(item, launch=self.reveal_launch)
        except RevealError:
            self._show_toast("File not found — cannot play")
        except KeyError:
            self._show_toast("File not found — cannot play")

    def reveal_library_item(self, item_id: int) -> None:
        from frameforge.library.actions import reveal_library_item
        from frameforge.util.reveal import RevealError

        try:
            reveal_library_item(self.library.get(item_id), launch=self.reveal_launch)
        except RevealError:
            self._show_toast("File not found — cannot reveal")

    def upscale_library_item(self, item_id: int) -> None:
        from frameforge.library.actions import can_upscale_library_item, upscale_blocked_reason

        item = self.library.get(item_id)
        if not can_upscale_library_item(item):
            self._show_toast(upscale_blocked_reason(item) or "Upscale blocked")
            return
        if not item.job_id:
            self._show_toast("No queue job for this file")
            return
        job = self.repo.get(item.job_id)
        if getattr(job, "upscale_blocked", False):
            self._show_toast("Upscale blocked: 4K / ≥2160p")
            return
        if hasattr(self.worker, "request_upscale_ids"):
            self.worker.request_upscale_ids([item.job_id])
        self._show_toast("Queued for upscale")
        self.refresh_queue(force=True)

    def open_new_collection(self, _e: Any = None) -> ft.AlertDialog:
        dlg = create_collection_dialog(
            on_create=self.create_library_collection,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("library_collection", dlg)

    def create_library_collection(self, name: str) -> Any:
        label = (name or "").strip()
        if not label:
            return None
        col = self.library.create_collection(label)
        self.close_dialog()
        self.refresh_library()
        return col

    def open_add_to_collection(self, _e: Any = None) -> ft.AlertDialog | None:
        if not self.library_selected_ids:
            self._show_toast("Select clips first")
            return None
        cols = [
            c
            for c in self.library.list_collections()
            if c.kind in {"type", "custom", "subject"}
        ]
        dlg = add_to_collection_dialog(
            cols,
            on_apply=self.apply_library_collections,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("library_tag", dlg)

    def apply_library_collections(self, collection_ids: list[int]) -> None:
        from frameforge.library.ingest import assign_to_collection

        ids = sorted(self.library_selected_ids)
        folder_ids = []
        tag_ids = []
        for cid in collection_ids:
            col = self.library.get_collection(cid)
            if col.uses_folder:
                folder_ids.append(cid)
            else:
                tag_ids.append(cid)
        primary = folder_ids[0] if folder_ids else None
        if primary is not None:
            assign_to_collection(self.repo, self.library, ids, primary, make_primary=True)
            for extra in folder_ids[1:]:
                assign_to_collection(self.repo, self.library, ids, extra, make_primary=False)
        for cid in tag_ids:
            assign_to_collection(self.repo, self.library, ids, cid, make_primary=False)
        self.close_dialog()
        self.refresh_library()

    def select_library_tab(self) -> None:
        if self.tabs is not None:
            self.tabs.selected_index = 2
        self.on_library_opened()

    def toggle_library_favorite(self, item_id: int) -> None:
        item = self.library.get(item_id)
        self.library.set_flags(item_id, is_favorite=not item.is_favorite)
        self.refresh_library()

    def toggle_library_watch_later(self, item_id: int) -> None:
        item = self.library.get(item_id)
        self.library.set_flags(item_id, watch_later=not item.watch_later)
        self.refresh_library()

    def upscale_library_selected(self) -> None:
        from frameforge.library.actions import can_upscale_library_item

        job_ids = []
        for item_id in sorted(self.library_selected_ids):
            item = self.library.get(item_id)
            if can_upscale_library_item(item) and item.job_id:
                job_ids.append(item.job_id)
        if job_ids and hasattr(self.worker, "request_upscale_ids"):
            self.worker.request_upscale_ids(job_ids)
            self._show_toast(f"Queued {len(job_ids)} for upscale")
        elif not job_ids:
            self._show_toast("No eligible clips (need height < 2160 and a queue job)")
        self.refresh_queue(force=True)

    def confirm_library_remove(self, *, delete_files: bool) -> ft.AlertDialog | None:
        n = len(self.library_selected_ids)
        if not n:
            return None
        dlg = confirm_remove_dialog(
            n,
            delete_files=delete_files,
            on_yes=lambda: self.apply_library_remove(delete_files=delete_files),
            on_close=self.close_dialog,
        )
        return self.dialogs.open("library_remove", dlg)

    def apply_library_remove(self, *, delete_files: bool) -> None:
        from frameforge.util.recycle import send_to_recycle_bin

        ids = sorted(self.library_selected_ids)
        for item_id in ids:
            item = self.library.get(item_id)
            path = Path(item.path)
            self.library.remove_item(item_id)
            if delete_files and path.is_file():
                send_to_recycle_bin(path, recycle=self.reveal_launch)
        self.library_selected_ids.clear()
        self.close_dialog()
        self.refresh_library()

    def pick_watch_folder(self, _e: Any = None) -> None:
        if self.page is None:
            return
        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            runner(self._pick_watch_folder)

    async def _pick_watch_folder(self) -> None:
        picker = self._ensure_file_picker()
        getter = getattr(picker, "get_directory_path", None)
        if not callable(getter):
            return
        path = await getter(dialog_title="Add extra folder")
        if path:
            self.add_library_watch_folder(path)

    def add_library_watch_folder(self, path: str | Path, *, import_mode: str = "index") -> None:
        from frameforge.library.ingest import index_folder

        dest = self.library.add_watch_folder(path, import_mode=import_mode)
        if import_mode == "index":
            index_folder(self.library, dest)
        else:
            from frameforge.library.ingest import import_folder

            import_folder(self.library, dest)
        self.refresh_library()

    def open_set_private_password(self, _e: Any = None) -> ft.AlertDialog:
        dlg = private_password_dialog(
            title="Set Private password",
            confirm=True,
            on_submit=self.apply_private_password,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("private_password", dlg)

    def apply_private_password(self, password: str) -> None:
        from frameforge.library.private import set_private_password

        set_private_password(self.library, password)
        self.private_session_password = password
        self.close_dialog()
        self._show_toast("Private password saved on this PC")

    def open_send_private(self, _e: Any = None) -> ft.AlertDialog | None:
        from frameforge.library.private import DEFAULT_DISGUISE, has_private_password

        if not self.library_selected_ids:
            return None
        if not has_private_password(self.library):
            return self.open_set_private_password()
        if not self.private_session_password:
            return self.open_private_unlock(next_action="send")
        dlg = send_private_dialog(
            len(self.library_selected_ids),
            disguise_default=DEFAULT_DISGUISE,
            on_confirm=self.confirm_send_private,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("send_private", dlg)

    def open_private_unlock(self, *, next_action: str = "unlock") -> ft.AlertDialog:
        def submit(pw: str) -> None:
            from frameforge.library.private import unlock_session

            if not unlock_session(self.library, pw):
                self._show_toast("Wrong password")
                return
            self.private_session_password = pw
            self.close_dialog()
            if next_action == "send":
                self.open_send_private()

        dlg = private_password_dialog(
            title="Unlock Private",
            confirm=False,
            on_submit=submit,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("private_unlock", dlg)

    def confirm_send_private(self, disguise: bool) -> None:
        from frameforge.library.private import send_to_private

        if not self.private_session_password:
            self._show_toast("Unlock Private first")
            return
        packs = send_to_private(
            self.library,
            sorted(self.library_selected_ids),
            password=self.private_session_password,
            disguise=disguise,
        )
        self._pending_private_packs = packs
        self.close_dialog()
        dlg = private_disposition_dialog(
            on_keep=lambda: self.dispose_private_originals("keep"),
            on_trash=lambda: self.dispose_private_originals("trash"),
            on_move=self.pick_private_originals_dest,
        )
        self.dialogs.open("private_disposition", dlg)

    def dispose_private_originals(self, mode: str, dest_dir: str | Path | None = None) -> None:
        from frameforge.library.private import dispose_originals

        originals = [p.original for p in self._pending_private_packs]
        dispose_originals(
            self.library,
            originals,
            mode=mode,
            dest_dir=dest_dir,
            recycle=self.reveal_launch,
        )
        self._pending_private_packs = []
        self.library_selected_ids.clear()
        self.close_dialog()
        self.refresh_library()

    def pick_private_originals_dest(self, _e: Any = None) -> None:
        if self.page is None:
            self.dispose_private_originals("keep")
            return
        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            runner(self._pick_private_originals_dest)

    async def _pick_private_originals_dest(self) -> None:
        picker = self._ensure_file_picker()
        getter = getattr(picker, "get_directory_path", None)
        if not callable(getter):
            return
        path = await getter(dialog_title="Move originals to folder")
        if path:
            self.dispose_private_originals("move", path)

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
        return self.open_quit_dialog()

    def open_quit_dialog(self) -> ft.AlertDialog:
        from frameforge.gui.exit_policy import list_active_work
        from frameforge.ui_flet.components.modals import quit_confirm_dialog

        busy = bool(list_active_work(self.repo))
        self.quit_choice: str | None = None

        def stay(_e=None) -> None:
            self.quit_choice = "cancel"
            self.close_dialog()
            self._close_clicks = 0

        def quit(_e=None) -> None:
            self.quit_choice = "quit"
            self.close_dialog()
            self._commit_quit()

        self.quit_dialog = quit_confirm_dialog(on_quit=quit, on_cancel=stay, busy=busy)
        return self.dialogs.open("quit", self.quit_dialog)

    def force_quit(self) -> None:
        """Same as Quit — hard-kill children and exit. Kept for tests / second X."""
        self._commit_quit()

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
        val = self.bridge.validate_site_cookies(raw, probe=getattr(self, "cookie_probe", None))
        if not val.ok:
            self._set_auth_error(val.message)
            return
        self.bridge.enable_gentle_after_bot()
        self._set_auth_error(
            (val.message or "Cookies look valid.") + " Close this dialog when you are ready.",
            ok=True,
        )

    def _auth_domain_value(self) -> str:
        dlg = getattr(self, "auth_dialog", None)
        data = getattr(dlg, "data", None) or {}
        field = data.get("field")
        return (getattr(field, "value", None) or "").strip()

    def _auth_error_control(self) -> Any | None:
        dlg = getattr(self, "auth_dialog", None)
        data = getattr(dlg, "data", None) or {}
        return data.get("error")

    def _set_auth_error(self, text: str, *, ok: bool = False) -> None:
        err = self._auth_error_control()
        if err is None:
            return
        err.value = text
        err.visible = bool(text)
        err.color = COLORS["success"] if ok else COLORS["danger"]
        if self.page is not None:
            self.page.update()

    def _auth_from_browser(self, browser: str, _e: Any = None) -> None:
        raw = self._auth_domain_value()
        if not raw:
            self._set_auth_error("Enter a site URL or domain first.")
            return
        result = self.import_cookies_from_browser_for_site(raw, browser=browser)
        if not getattr(result, "ok", False):
            self._set_auth_error(
                getattr(result, "message", None) or f"{browser.capitalize()} import failed."
            )
            return
        val = self.bridge.validate_site_cookies(raw, probe=getattr(self, "cookie_probe", None))
        if not val.ok:
            self._set_auth_error(val.message)
            return
        self.bridge.enable_gentle_after_bot()
        self._set_auth_error(
            (val.message or "Cookies look valid.") + " Close this dialog when you are ready.",
            ok=True,
        )

    def _auth_firefox(self, _e: Any = None) -> None:
        self._auth_from_browser("firefox", _e)

    def _auth_chrome(self, _e: Any = None) -> None:
        self._auth_from_browser("chrome", _e)

    def _auth_edge(self, _e: Any = None) -> None:
        self._auth_from_browser("edge", _e)

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
            on_chrome=self._auth_chrome,
            on_edge=self._auth_edge,
            on_firefox=self._auth_firefox,
            on_txt=self._auth_choose_txt,
            on_copy=self._copy_auth_error,
            on_open_cookies=self.open_cookies_folder,
            on_close=self.close_dialog,
        )
        return self.dialogs.open("auth", self.auth_dialog)

    def open_settings(self) -> ft.AlertDialog:
        if self.dialogs.kind == "settings" and self.dialogs.current is not None:
            return self.dialogs.open("settings", self.dialogs.current)
        if self.bridge.settings_open and self.settings_dialog is not None:
            return self.dialogs.open("settings", self.settings_dialog)

        if self._repair_status is None:
            self._repair_status = ft.Text("", size=12, color=COLORS["text_secondary"])
        if self._repair_button is None:
            self._repair_button = ft.OutlinedButton(
                content="Repair folders",
                on_click=lambda _e: self.repair_folders(),
            )
        self._repair_button.disabled = bool(self._repair_busy)
        if self._repair_busy:
            self._repair_status.value = self._repair_status.value or "Repairing folders…"

        self.settings_dialog = build_settings_dialog(
            self.repo,
            on_close=self.close_dialog,
            on_open_cookies=self.open_cookies_folder,
            library=self.library,
            on_pick_library_root=self.pick_library_root,
            on_pick_watch_folder=self.pick_watch_folder,
            on_set_private_password=self.open_set_private_password,
            on_reset_library=self.open_reset_library,
            on_repair_folders=self.repair_folders,
            repair_status=self._repair_status,
            repair_button=self._repair_button,
        )
        return self.dialogs.open("settings", self.settings_dialog)

    def open_reset_library(self, _e: Any = None) -> ft.AlertDialog:
        dlg = confirm_reset_library_dialog(on_yes=self.confirm_reset_library, on_close=self.close_dialog)
        return self.dialogs.open("reset_library", dlg)

    def confirm_reset_library(self, _e: Any = None) -> None:
        from frameforge.library.reset import reset_library_state

        reset_library_state(self.library)
        self.close_dialog()
        self.refresh_library()
        self._show_toast("Library onboarding reset — media files were not deleted")
        self.on_library_opened()

    def repair_folders(self, _e: Any = None) -> None:
        self._start_tree_repair(toast=True)

    def _apply_repair_progress(self, message: str) -> None:
        if self._repair_status is not None:
            self._repair_status.value = message
        page = self.page
        if page is not None:
            try:
                page.update()
            except Exception:  # noqa: BLE001
                pass

    def _start_tree_repair(self, *, toast: bool = False) -> None:
        thread = self._tree_repair_thread
        if thread is not None and thread.is_alive():
            self._apply_repair_progress("Repairing folders… (already running)")
            if toast:
                self._show_toast("Folder repair already running")
            return
        self._repair_busy = True
        if self._repair_button is not None:
            self._repair_button.disabled = True
        self._apply_repair_progress("Repairing folders…")
        db = self.repo.db_path

        def on_progress(message: str) -> None:
            self._marshal_ui(lambda m=message: self._apply_repair_progress(m))

        def _run() -> None:
            from frameforge.db.repository import JobRepository
            from frameforge.layout import repair_frameforge_tree
            from frameforge.paths import frameforge_root

            repo = JobRepository(db)
            error: str | None = None
            try:
                stats = repair_frameforge_tree(
                    frameforge_root(),
                    site_folders=True,
                    conn=repo.conn,
                    on_progress=on_progress,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("Folder repair failed")
                stats = {
                    "thumbs": 0,
                    "db": 0,
                    "videos": 0,
                    "junk_candidates": 0,
                    "junk_relocated": 0,
                    "json_moved": 0,
                    "thumb_paths_updated": 0,
                }
                error = str(exc)
            finally:
                try:
                    repo.close()
                except Exception:  # noqa: BLE001
                    pass
            self._marshal_ui(lambda: self._on_tree_repair_done(stats, toast=toast, error=error))

        self._tree_repair_thread = threading.Thread(target=_run, name="frameforge-tree-repair", daemon=True)
        self._tree_repair_thread.start()

    def _on_tree_repair_done(
        self, stats: dict[str, int], *, toast: bool = False, error: str | None = None
    ) -> None:
        self._repair_busy = False
        if self._repair_button is not None:
            self._repair_button.disabled = False
        summary = (
            f"Repair: {int(stats.get('thumbs', 0))} thumbs, "
            f"{int(stats.get('junk_relocated', 0))} junk → temp/junk, "
            f"{int(stats.get('json_moved', 0))} info.json → metadata/"
        )
        if error:
            summary = f"Repair failed: {error}"
        self._apply_repair_progress(summary)
        try:
            self.refresh_queue(force=True)
        except Exception:
            log.exception("Queue refresh after folder repair failed")
        try:
            self.refresh_library()
        except Exception:
            log.exception("Library refresh after folder repair failed")
        if toast:
            self.dialogs.open(
                "repair_summary",
                repair_summary_dialog(stats, error=error, on_close=self.close_dialog),
            )

    def _on_keyboard(self, e: Any) -> None:
        key = getattr(e, "key", None)
        if key in {"Escape", "Esc"}:
            self.close_dialog()
            return
        ctrl = bool(getattr(e, "ctrl", False))
        if ctrl and str(key).upper() in {"Q"}:
            self.handle_window_close()
            return
        if ctrl and str(key) in {"3", "Digit3", "Numpad3"}:
            self.select_library_tab()

    def _on_window_event(self, e: Any) -> None:
        et = getattr(e, "type", None)
        name = str(getattr(et, "name", None) or getattr(et, "value", et) or "").lower()
        if "close" in name:
            self.handle_window_close()
            return
        if self._exiting or self._shutdown_complete:
            return
        if self.page is not None:
            self.last_chrome = apply_page_chrome(self.page, set_size=False)

    def _on_disconnect(self, _e: Any = None) -> None:
        if not self._shutdown_complete:
            self._commit_quit()

    def _release_native_close(self) -> None:
        page = self.page
        win = getattr(page, "window", None) if page is not None else None
        if win is None:
            return
        try:
            win.prevent_close = False
        except Exception:  # noqa: BLE001
            pass

    def _arm_exit_watchdog(self, seconds: float = SHUTDOWN_WATCHDOG_SEC) -> None:
        """If teardown hangs, kill Flet View children then _exit. Never starts a timer in pytest."""
        self._watchdog_armed = True
        self._watchdog_seconds = seconds
        if not self.exit_process_on_quit:
            return
        from frameforge.util.process_tree import schedule_hard_exit

        schedule_hard_exit(max(0.2, float(seconds)), 0)

    def handle_window_close(self, _e: Any = None) -> str:
        now = time.monotonic()
        if self._exiting or self._shutdown_complete:
            self._commit_quit()
            return "quit"
        if getattr(self.dialogs, "kind", None) == "quit":
            if now - self._last_close_event < CLOSE_DEBOUNCE_SEC:
                return "choice"
            self._commit_quit()
            return "quit"
        self._last_close_event = now
        self._close_clicks += 1
        try:
            dlg = self.open_quit_dialog()
            opened = dlg is not None and (
                bool(getattr(dlg, "open", False)) or self.dialogs.kind == "quit"
            )
            if not opened:
                self._commit_quit()
                return "quit"
            return "choice"
        except Exception:  # noqa: BLE001
            self._commit_quit()
            return "quit"

    def _finish_exit(self) -> None:
        self._commit_quit()

    def _commit_quit(self) -> None:
        """Quit: release prevent_close, cancel library move, kill children, destroy window.

        prevent_close is cleared first so X is never stuck behind a move. Library
        worker is signalled and joined up to LIBRARY_MOVE_JOIN_SEC; a watchdog
        still hard-exits if teardown hangs. Never waits on the Flet event loop.
        """
        if self._shutdown_complete:
            if self.exit_process_on_quit:
                from frameforge.util.process_tree import hard_exit

                hard_exit(0)
            return
        self._exiting = True
        self._release_native_close()
        move_running = self.library_move_running
        self.cancel_library_move()
        self._arm_exit_watchdog(5.0 if move_running else SHUTDOWN_WATCHDOG_SEC)
        try:
            self.close_dialog()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.wait_library_move(LIBRARY_MOVE_JOIN_SEC)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.worker.kill_active_processes()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.worker.stop(timeout=0.2)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.repo.close()
        except Exception:  # noqa: BLE001
            pass
        self._shutdown_complete = True
        from frameforge.ui_flet.window_teardown import request_window_destroy

        self.last_destroy_status = request_window_destroy(self.page, wait=0)
        if self.exit_process_on_quit:
            from frameforge.util.process_tree import schedule_hard_exit

            schedule_hard_exit(QUIT_HARD_EXIT_DELAY_SEC, 0)
        else:
            self._release_native_close()

    def _destroy_and_exit(self) -> None:
        self._commit_quit()

    def attach_page(self, page: ft.Page) -> None:
        self.page = page
        self.exit_process_on_quit = isinstance(page, ft.Page)
        self.last_chrome = apply_page_chrome(page, set_size=True)
        win = getattr(page, "window", None)
        if win is not None:
            win.prevent_close = True
            win.on_event = self._on_window_event
        page.on_disconnect = self._on_disconnect
        page.on_keyboard_event = self._on_keyboard
        page.on_close = self.handle_window_close
        self._ensure_file_picker()
        page.add(self.build())
        self._schedule_tick()
        self._start_tree_repair(toast=False)

    def shutdown(self) -> None:
        try:
            self.cancel_library_move()
            self.wait_library_move(LIBRARY_MOVE_JOIN_SEC)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.worker.stop(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.repo.close()
        except Exception:  # noqa: BLE001
            pass


def build_header_default() -> ft.Row:
    return build_header()


def build_shell() -> ft.Column:
    """Light chrome: header + hero + Queue/History/Library placeholders (no backend)."""
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
            ui._exiting = True
            try:
                ui.worker.kill_active_processes()
            except Exception:  # noqa: BLE001
                pass
            ui.shutdown()
            ui._shutdown_complete = True
        if ui.exit_process_on_quit:
            from frameforge.util.process_tree import hard_exit

            hard_exit(0)
