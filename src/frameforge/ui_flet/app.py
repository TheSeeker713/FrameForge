"""Flet desktop shell — light FrameForge window."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import flet as ft

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
from frameforge.ui_flet.theme import COLORS, TAB_LABELS
from frameforge.ui_flet.window_chrome import apply_page_chrome, build_custom_title_bar

_GUI_RUNNING = False
SHUTDOWN_WATCHDOG_SEC = 3.0


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
        self.title_bar: ft.Control | None = None
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
        self._watchdog_armed = False
        self._watchdog_seconds = SHUTDOWN_WATCHDOG_SEC
        self._import_preview: Any | None = None
        self._pending_import = False
        self._browser_cookie_runner: Any | None = None
        self.import_browser_fn: Any | None = None
        self.last_more_action: str | None = None
        self.more_invocations: list[str] = []
        self._activity_note: str | None = None
        self._action_lock = False
        self.last_chrome: dict[str, Any] | None = None
        self.last_copied_report: str | None = None
        self.last_destroy_status: str | None = None
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
        status = ft.Text("", color=COLORS["warn"], visible=False)

        def retry_resume(_e=None) -> None:
            self.bridge.handle_fail_pause_action("retry_resume", jid)
            self.close_dialog()
            self.refresh_queue()

        resume_btn = elevated_filled_button("Retry this job and resume queue", on_click=retry_resume)
        resume_btn.visible = False
        browser_pick = ft.Dropdown(
            label="Browser",
            value="chrome",
            options=[
                ft.dropdown.Option("chrome", text="Chrome"),
                ft.dropdown.Option("edge", text="Edge"),
                ft.dropdown.Option("firefox", text="Firefox"),
            ],
            width=220,
        )

        def act(aid: str):
            def _(_e=None):
                if aid == "authenticate":
                    url = payload.get("url")
                    self.open_authenticate(prefill=url)
                    return
                if aid == "import_browser":
                    url = str(payload.get("url") or "")
                    chosen = (browser_pick.value or "chrome").strip().lower()
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
                        "Pick Chrome, Edge, or Firefox, import cookies, then retry only after they validate.",
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
                elevated_filled_button("Import from browser", on_click=act("import_browser")),
                elevated_outlined_button("Authenticate site", on_click=act("authenticate")),
                elevated_outlined_button("Retry this job", on_click=act("retry")),
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
            setter = getattr(page, "set_clipboard", None)
            if callable(setter):
                try:
                    setter(text)
                except Exception:  # noqa: BLE001
                    pass
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
        self.title_bar = build_custom_title_bar(
            on_close=self.handle_window_close,
            on_min=self.minimize_window,
            on_max=self.toggle_maximize,
            on_drag_start=self._on_title_drag_start,
            on_drag_end=self._on_title_drag_end,
        )
        root = ft.Column(
            expand=True,
            spacing=16,
            controls=[
                self.title_bar,
                self.header,
                self.hero,
                self.undo_banner,
                self.resource_banner,
                self.tabs,
            ],
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
        text = self._activity_note or status_from_repo(self.repo, self.worker)
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
        self._activity_note = "Stopped"
        self.refresh_queue(force=True)

    def tick(self) -> None:
        """Poll SQLite into the cards. Tests call this; the live window schedules it."""
        if self._exiting or self._shutdown_complete:
            return
        active = next(
            (j for j in self.queue_jobs() if j.status in {"downloading", "upscaling", "converting"}),
            None,
        )
        if active is not None:
            self._activity_note = None
        self.refresh_queue()
        self._sync_header()
        if self.page is not None:
            self.last_chrome = apply_page_chrome(self.page, set_size=False)

    def _schedule_tick(self) -> None:
        if self._exiting or self._shutdown_complete or not self.exit_process_on_quit:
            return
        try:
            self.tick()
        except Exception:  # noqa: BLE001
            pass
        if self._exiting or self._shutdown_complete:
            return
        delay = 0.4 if getattr(self.worker, "is_armed", False) else 1.5
        timer = threading.Timer(delay, self._schedule_tick)
        timer.daemon = True
        timer.start()

    def toggle_failed_expand(self, job_id: int) -> None:
        if job_id in self.expanded_failed:
            self.expanded_failed.discard(job_id)
        else:
            self.expanded_failed.add(job_id)
        self.refresh_queue(force=True)

    def retry_failed_job(self, job_id: int) -> None:
        self._activity_note = "Retrying…"
        self.bridge.retry_job(job_id)
        if not self.worker.is_armed:
            self._activity_note = "Retry did not start — worker is not armed."
        self.refresh_queue(force=True)

    def retry_all_failed(self) -> list[int]:
        self._activity_note = "Retrying failed jobs…"
        ids = self.bridge.retry_all_failed()
        if ids and not self.worker.is_armed:
            self._activity_note = "Retry did not start — worker is not armed."
        elif not ids:
            self._activity_note = "No failed jobs to retry."
        self.refresh_queue(force=True)
        return ids

    def retry_selected_failed(self) -> list[int]:
        if self._action_lock:
            return []
        self._action_lock = True
        try:
            self._activity_note = "Retrying selected…"
            ids = self.bridge.retry_failed_ids(sorted(self.selected_ids))
            if ids and not self.worker.is_armed:
                self._activity_note = "Retry did not start — worker is not armed."
            elif not ids:
                self._activity_note = "Nothing to retry in the selection."
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
            self.bridge.clear_history_ids(sorted(self.selected_ids))
            self._sync_undo_banner()
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
        return self.open_quit_dialog()

    def open_quit_dialog(self) -> ft.AlertDialog:
        from frameforge.gui.exit_policy import (
            CHOICE_FORCE_QUIT,
            CHOICE_QUIT_IDLE,
            CHOICE_STAY,
            NEEDS_CHOICE,
            OUTCOME_EXIT,
            OUTCOME_FORCE,
            OUTCOME_WAIT,
            WAIT_IN_PROGRESS,
            apply_quit_choice,
            classify_exit,
        )
        from frameforge.ui_flet.components.modals import quit_busy_dialog

        kind = classify_exit(self.repo, self.worker)
        busy = kind in (NEEDS_CHOICE, WAIT_IN_PROGRESS)
        self.quit_choice: str | None = None

        def choose(c: str) -> None:
            self.quit_choice = c
            if c == CHOICE_STAY:
                self.close_dialog()
                self._close_clicks = 0
                return
            self.close_dialog()
            outcome = apply_quit_choice(self.worker, c)
            if c == CHOICE_FORCE_QUIT or outcome == OUTCOME_FORCE:
                self.force_quit()
                return
            if outcome == OUTCOME_WAIT:
                self._close_clicks = 0
                return
            if outcome == OUTCOME_EXIT or c == CHOICE_QUIT_IDLE:
                self._finish_exit()

        self.quit_dialog = quit_busy_dialog(
            on_choice=choose,
            on_cancel=lambda _e=None: choose(CHOICE_STAY),
            busy=busy,
        )
        return self.dialogs.open("quit", self.quit_dialog)

    def force_quit(self) -> None:
        """Always-available escape: await window destroy, kill flet children, _exit."""
        self._exiting = True
        self._close_clicks = 99
        self._release_native_close()
        self._arm_exit_watchdog(0.5)
        try:
            self.worker.stop(timeout=0.5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.repo.close()
        except Exception:  # noqa: BLE001
            pass
        self._shutdown_complete = True
        from frameforge.ui_flet.window_teardown import request_window_destroy
        from frameforge.util.process_tree import force_kill_current_app, kill_gui_children

        self.last_destroy_status = request_window_destroy(self.page, wait=0.4)
        if self.exit_process_on_quit:
            try:
                kill_gui_children()
            except Exception:  # noqa: BLE001
                pass
            force_kill_current_app()
        else:
            self._release_native_close()

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
            return
        ctrl = bool(getattr(e, "ctrl", False))
        if ctrl and str(key).upper() in {"Q"}:
            self.handle_window_close()

    def _on_window_event(self, e: Any) -> None:
        if self.page is not None:
            self.last_chrome = apply_page_chrome(self.page, set_size=False)
        et = getattr(e, "type", None)
        name = str(getattr(et, "name", None) or getattr(et, "value", et) or "").lower()
        if any(tok in name for tok in ("close", "close_prevented")):
            self.handle_window_close()

    def _on_disconnect(self, _e: Any = None) -> None:
        if not self._shutdown_complete:
            self._release_native_close()
            self._finish_exit()

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
        """If teardown hangs, kill the process. Never starts a timer in pytest."""
        self._watchdog_armed = True
        self._watchdog_seconds = seconds
        if not self.exit_process_on_quit:
            return
        timer = threading.Timer(max(0.2, float(seconds)), lambda: os._exit(1))
        timer.daemon = True
        timer.start()

    def handle_window_close(self, _e: Any = None) -> str:
        self._close_clicks += 1
        force = self._close_clicks >= 2 or self._exiting
        if force:
            self.force_quit()
            return "force"
        try:
            dlg = self.open_quit_dialog()
            opened = dlg is not None and (
                bool(getattr(dlg, "open", False)) or self.dialogs.kind == "quit"
            )
            if not opened:
                self.force_quit()
                return "exit"
            return "choice"
        except Exception:  # noqa: BLE001
            self.force_quit()
            return "exit"

    def _finish_exit(self) -> None:
        if self._shutdown_complete:
            if self.exit_process_on_quit:
                os._exit(0)
            return
        self._exiting = True
        self._release_native_close()
        self._arm_exit_watchdog()
        try:
            self.close_dialog()
        except Exception:  # noqa: BLE001
            pass
        self.shutdown()
        self._shutdown_complete = True
        if self.exit_process_on_quit:
            self._destroy_and_exit()

    def _destroy_and_exit(self) -> None:
        from frameforge.ui_flet.window_teardown import request_window_destroy
        from frameforge.util.process_tree import kill_gui_children

        self.last_destroy_status = request_window_destroy(self.page, wait=0.8)
        try:
            kill_gui_children()
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)

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

    def shutdown(self) -> None:
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
            ui._exiting = True
            ui._arm_exit_watchdog()
            ui.shutdown()
            ui._shutdown_complete = True
        if ui.exit_process_on_quit:
            os._exit(0)
