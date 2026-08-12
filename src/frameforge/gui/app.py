"""FrameForge CustomTkinter application."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import confirm_add, preview_import
from frameforge.gui.queue_list import QueueList
from frameforge.paths import db_path, ensure_output_tree
from frameforge.pipeline import build_worker
from frameforge.queue.worker import SequentialWorker


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class FrameForgeApp(ctk.CTk):
    def __init__(
        self,
        repo: JobRepository | None = None,
        *,
        start_worker: bool = False,
        tray_icon_factory: Any | None = None,
    ):
        """GUI defaults to idle worker (start_worker=False). Downloads start only on demand."""
        super().__init__()
        ensure_output_tree()
        self.title("FrameForge")
        self.geometry("1000x680")
        self.repo = repo or JobRepository(db_path())
        self.worker: SequentialWorker = build_worker(self.repo)
        self._selected_ids: set[int] = set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        header = ctk.CTkLabel(self, text="FrameForge", font=ctk.CTkFont(size=28, weight="bold"))
        header.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")

        self.seq_banner = ctk.CTkLabel(
            self,
            text="Downloads run one at a time — queue only until you press Download",
            text_color="#9ad0ff",
        )
        self.seq_banner.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=2, column=0, padx=16, pady=(0, 4), sticky="ew")
        self.progress_bar.set(0)
        self.progress_label = ctk.CTkLabel(self, text="Idle — 0% | — | ETA —")
        self.progress_label.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="w")

        entry_row = ctk.CTkFrame(self, fg_color="transparent")
        entry_row.grid(row=4, column=0, padx=16, pady=8, sticky="ew")
        entry_row.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(entry_row, placeholder_text="Paste video URL…")
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.add_btn = ctk.CTkButton(entry_row, text="Add", width=90, command=self.add_url)
        self.add_btn.grid(row=0, column=1, padx=(0, 8))
        self.import_btn = ctk.CTkButton(
            entry_row, text="Import TXT/MD", width=120, command=self.import_file
        )
        self.import_btn.grid(row=0, column=2, padx=(0, 8))
        self.auth_btn = ctk.CTkButton(
            entry_row, text="Authenticate site…", width=140, command=self.authenticate_site
        )
        self.auth_btn.grid(row=0, column=3, padx=(0, 8))
        self.settings_btn = ctk.CTkButton(
            entry_row, text="Settings", width=90, command=self.open_settings
        )
        self.settings_btn.grid(row=0, column=4)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=5, column=0, padx=16, pady=8, sticky="nsew")
        self.tabs.add("Queue")
        self.tabs.add("History")
        qtab = self.tabs.tab("Queue")
        qtab.grid_columnconfigure(0, weight=1)
        qtab.grid_rowconfigure(0, weight=1)
        self.queue_list = QueueList(
            qtab,
            on_selection_changed=self._on_queue_selection_changed,
            label_text="Queue",
        )
        self.queue_list.grid(row=0, column=0, sticky="nsew")
        self.queue_box = self.queue_list

        htab = self.tabs.tab("History")
        htab.grid_columnconfigure(0, weight=1)
        htab.grid_rowconfigure(1, weight=1)
        hbar = ctk.CTkFrame(htab, fg_color="transparent")
        hbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.history_filter = ctk.CTkSegmentedButton(
            hbar,
            values=["All", "Completed", "Failed"],
            command=lambda _v: self.refresh_history(),
        )
        self.history_filter.set("All")
        self.history_filter.pack(side="left", padx=(0, 8))
        self.history_search = ctk.CTkEntry(hbar, placeholder_text="Search title / URL / site")
        self.history_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.history_search.bind("<Return>", lambda _e: self.refresh_history())
        self.history_retry_btn = ctk.CTkButton(
            hbar, text="Retry selected", width=120, command=self.retry_history_selected
        )
        self.history_retry_btn.pack(side="left", padx=(0, 8))
        self.history_hide_btn = ctk.CTkButton(
            hbar, text="Hide selected", width=120, command=self.hide_history_selected
        )
        self.history_hide_btn.pack(side="left")
        self.history_list = QueueList(
            htab,
            on_selection_changed=self._on_history_selection_changed,
            label_text="History",
            show_timestamps=True,
        )
        self.history_list.grid(row=1, column=0, sticky="nsew")

        self.tabs.add("Thumbnails")
        ttab = self.tabs.tab("Thumbnails")
        ttab.grid_columnconfigure(0, weight=1)
        ttab.grid_rowconfigure(0, weight=1)
        self.thumbs_frame = ctk.CTkScrollableFrame(ttab, label_text="Thumbnails")
        self.thumbs_frame.grid(row=0, column=0, sticky="nsew")
        self._thumb_tab_widgets: list[Any] = []
        self._thumb_tab_sig: tuple[str, ...] | None = None
        self.tabs.configure(command=self._on_tab_changed)

        detail = ctk.CTkFrame(self, fg_color="transparent")
        detail.grid(row=6, column=0, padx=16, pady=(0, 4), sticky="ew")
        detail.grid_columnconfigure(0, weight=1)
        self.error_panel_label = ctk.CTkLabel(
            detail, text="Job errors / details", anchor="w", text_color="#c8c8c8"
        )
        self.error_panel_label.grid(row=0, column=0, sticky="w")
        self.auth_from_job_btn = ctk.CTkButton(
            detail,
            text="Authenticate this site…",
            width=180,
            command=self.authenticate_selected_job,
            state="disabled",
        )
        self.auth_from_job_btn.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.import_browser_from_job_btn = ctk.CTkButton(
            detail,
            text="Import from browser…",
            width=180,
            command=self.import_browser_selected_job,
            state="disabled",
        )
        self.import_browser_from_job_btn.grid(row=0, column=2, sticky="e")
        detail.grid_columnconfigure(1, weight=0)
        detail.grid_columnconfigure(2, weight=0)
        self.error_panel = ctk.CTkTextbox(detail, height=88, wrap="word")
        self.error_panel.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.error_panel.configure(state="disabled")
        self._set_error_panel_text("")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=7, column=0, padx=16, pady=(4, 16), sticky="ew")
        self.download_selected_btn = ctk.CTkButton(
            controls, text="Download selected", command=self.download_selected
        )
        self.download_selected_btn.pack(side="left", padx=(0, 8))
        self.download_all_btn = ctk.CTkButton(
            controls, text="Download all pending", command=self.download_all_pending
        )
        self.download_all_btn.pack(side="left", padx=(0, 8))
        self.upscale_selected_btn = ctk.CTkButton(
            controls, text="Upscale selected (2×)", command=self.upscale_selected
        )
        self.upscale_selected_btn.pack(side="left", padx=(0, 8))
        self.select_recommended_btn = ctk.CTkButton(
            controls, text="Select recommended", command=self.select_recommended
        )
        self.select_recommended_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ctk.CTkButton(controls, text="Stop after current", command=self.stop_worker)
        self.stop_btn.pack(side="left", padx=(0, 8))
        self.cancel_btn = ctk.CTkButton(controls, text="Cancel selected", command=self.cancel_selected)
        self.cancel_btn.pack(side="left", padx=(0, 8))
        self.pause_btn = ctk.CTkButton(controls, text="Pause", command=self.pause_selected)
        self.pause_btn.pack(side="left", padx=(0, 8))
        self.resume_btn = ctk.CTkButton(controls, text="Resume", command=self.resume_selected)
        self.resume_btn.pack(side="left", padx=(0, 8))
        self.set_format_btn = ctk.CTkButton(
            controls, text="Set format…", command=self.set_format_selected
        )
        self.set_format_btn.pack(side="left", padx=(0, 8))
        self.retry_btn = ctk.CTkButton(controls, text="Retry failed", command=self.retry_failed)
        self.retry_btn.pack(side="left", padx=(0, 8))
        self.prio_up_btn = ctk.CTkButton(
            controls, text="Priority +", command=lambda: self.bump_priority(1)
        )
        self.prio_up_btn.pack(side="left", padx=(0, 8))
        self.prio_down_btn = ctk.CTkButton(
            controls, text="Priority -", command=lambda: self.bump_priority(-1)
        )
        self.prio_down_btn.pack(side="left", padx=(0, 8))
        self.open_folder_btn = ctk.CTkButton(
            controls, text="Open folder", command=self.open_folder_selected
        )
        self.open_folder_btn.pack(side="left", padx=(0, 8))
        self.reveal_file_btn = ctk.CTkButton(
            controls, text="Reveal file", command=self.reveal_file_selected
        )
        self.reveal_file_btn.pack(side="left", padx=(0, 8))
        self.refresh_btn = ctk.CTkButton(controls, text="Refresh", command=self.refresh_queue)
        self.refresh_btn.pack(side="left")

        self.bind("<Control-v>", self._paste_focus)
        self.bind("<Control-Return>", lambda e: self.add_url())
        self.bind("<Control-q>", lambda e: self.request_quit())
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._build_menubar()
        self._shutting_down = False
        from frameforge.gui.tray import TrayService

        self.tray = TrayService(
            widget=self,
            on_show=lambda: self.marshal_ui(self.show_from_tray),
            on_pause_resume=lambda: self.marshal_ui(self._tray_pause_resume),
            on_quit=lambda: self.marshal_ui(lambda: self.request_quit()),
            pause_resume_label=self._tray_pause_resume_label,
            icon_factory=tray_icon_factory,
        )

        if start_worker:
            self.worker.request_download_all()

        self.refresh_queue()
        self.after(1000, self._tick)

    def marshal_ui(self, fn) -> None:
        """Run *fn* on the Tk thread (tray callbacks must not touch CTk directly)."""
        try:
            self.after(0, fn)
        except Exception:  # noqa: BLE001
            fn()

    def _close_to_tray_enabled(self) -> bool:
        return self.repo.get_setting("close_to_tray", "0") == "1"

    def hide_to_tray(self) -> None:
        self.withdraw()
        try:
            self.tray.start()
        except Exception:  # noqa: BLE001
            pass

    def show_from_tray(self) -> None:
        self.deiconify()
        try:
            self.lift()
            self.focus_force()
        except Exception:  # noqa: BLE001
            pass

    def _tray_pause_resume_label(self) -> str:
        from frameforge.gui.exit_policy import list_active_work

        active = list_active_work(self.repo)
        if active:
            return "Pause current"
        paused = self.repo.list_jobs("paused")
        if paused:
            return "Resume current"
        return "Pause current / Resume current"

    def _tray_pause_resume(self) -> None:
        from frameforge.gui.actions import can_pause, can_resume
        from frameforge.gui.exit_policy import list_active_work

        for job in list_active_work(self.repo):
            if can_pause(job):
                self.worker.pause_job(job.id)
                self.refresh_queue()
                return
        for job in self.repo.list_jobs("paused"):
            if can_resume(job):
                self.worker.resume_job(job.id)
                self.refresh_queue()
                return

    def _on_window_close(self) -> None:
        if self._close_to_tray_enabled():
            self.hide_to_tray()
            return
        self.request_quit()

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Quit", command=self.request_quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.configure(menu=menubar)

    def request_quit(self) -> None:
        """Window X, File→Quit, Ctrl+Q, and tray Quit all use this policy."""
        from frameforge.gui.exit_policy import (
            NEEDS_CHOICE,
            OUTCOME_EXIT,
            QUIT_NOW,
            WAIT_IN_PROGRESS,
            apply_quit_choice,
            ask_quit_while_busy,
            classify_exit,
        )

        if self._shutting_down:
            return
        kind = classify_exit(self.repo, self.worker)
        if kind == WAIT_IN_PROGRESS:
            return
        if kind == QUIT_NOW:
            self._finish_quit()
            return
        assert kind == NEEDS_CHOICE
        chooser = getattr(self, "_ask_quit_choice", None)
        choice = chooser() if chooser else ask_quit_while_busy(self)
        if not choice:
            return
        outcome = apply_quit_choice(self.worker, choice)
        if outcome == OUTCOME_EXIT:
            self._finish_quit()

    def _finish_quit(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.shutdown()
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _on_selection_changed(self, ids: set[int]) -> None:
        self._on_queue_selection_changed(ids)

    def _on_queue_selection_changed(self, ids: set[int]) -> None:
        if self._active_tab_name() != "History":
            self._selected_ids = set(ids)
            self._update_error_panel()

    def _on_history_selection_changed(self, ids: set[int]) -> None:
        if self._active_tab_name() == "History":
            self._selected_ids = set(ids)
            self._update_error_panel()

    def _active_tab_name(self) -> str:
        try:
            return str(self.tabs.get())
        except Exception:  # noqa: BLE001
            return "Queue"

    def _on_tab_changed(self, *_args: Any) -> None:
        name = self._active_tab_name()
        if name == "History":
            self.refresh_history()
            self._selected_ids = self.history_list.selected_ids
        elif name == "Thumbnails":
            self.refresh_thumbnails()
        else:
            self._selected_ids = self.queue_list.selected_ids
        self._update_error_panel()

    def _selected_job_ids(self) -> list[int]:
        if self._active_tab_name() == "History":
            return sorted(self._selected_ids or self.history_list.selected_ids)
        return sorted(self._selected_ids or self.queue_list.selected_ids)

    def _set_error_panel_text(self, text: str) -> None:
        self.error_panel.configure(state="normal")
        self.error_panel.delete("1.0", "end")
        if text:
            self.error_panel.insert("1.0", text)
        self.error_panel.configure(state="disabled")

    @staticmethod
    def format_error_panel_text(job: Any | None) -> str:
        """Category + message + suggested next action (auth, retry, lower-res, …)."""
        from frameforge.errors import format_error_panel

        return format_error_panel(job)

    def _update_error_panel(self) -> None:
        ids = self._selected_ids
        if not ids:
            self._set_error_panel_text("")
            self.error_panel_label.configure(text="Job errors / details")
            self.auth_from_job_btn.configure(state="disabled")
            self.import_browser_from_job_btn.configure(state="disabled")
            return
        jid = sorted(ids)[0]
        try:
            job = self.repo.get(jid)
        except Exception:  # noqa: BLE001
            self._set_error_panel_text("")
            self.auth_from_job_btn.configure(state="disabled")
            self.import_browser_from_job_btn.configure(state="disabled")
            return
        text = self.format_error_panel_text(job)
        if text:
            self.error_panel_label.configure(
                text=f"Job errors / details — #{job.id} [{job.status}]"
            )
        else:
            self.error_panel_label.configure(
                text=f"Job errors / details — #{job.id} [{job.status}] (no errors)"
            )
        self._set_error_panel_text(text)
        from frameforge.download.auth_hints import job_needs_auth

        need = job_needs_auth(job)
        self.auth_from_job_btn.configure(state="normal" if need else "disabled")
        self.import_browser_from_job_btn.configure(state="normal" if need else "disabled")

    def _paste_focus(self, _event=None):
        self.url_entry.focus_set()

    def _default_upscale(self) -> bool:
        return self.repo.get_setting("upscale_after_download", "0") == "1"

    def _default_format(self) -> str:
        return self.repo.get_setting("format_preference", "best") or "best"

    def add_url(self) -> None:
        url = self.url_entry.get().strip()
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showerror("FrameForge", "Enter a valid http(s) URL")
            return
        from frameforge.download.playlist import extract_playlist, looks_like_playlist_url

        extract_fn = getattr(self, "_playlist_extract_fn", None)
        listing = None
        if extract_fn is not None or looks_like_playlist_url(url):
            try:
                listing = extract_playlist(url, extract_fn=extract_fn)
            except Exception:  # noqa: BLE001
                listing = None
        if listing and listing.entries:
            self.url_entry.delete(0, "end")
            self._open_playlist_picker(listing)
            return
        self._enqueue_single_url(url)
        self.url_entry.delete(0, "end")
        self.refresh_queue()

    def _enqueue_single_url(self, url: str) -> None:
        from frameforge.download.metadata import probe_listing_bundle
        from frameforge.download.thumbnails import cache_job_thumbnail

        title, extractor, thumb_url = probe_listing_bundle(url)
        job = self.repo.enqueue(
            url,
            title=title,
            extractor=extractor,
            format_preference=self._default_format(),
            upscale=self._default_upscale(),
        )
        cache_job_thumbnail(self.repo, job.id, thumbnail_url=thumb_url)

    def _open_playlist_picker(self, listing) -> None:
        from frameforge.gui.playlist_picker import PlaylistPicker

        def on_confirm(indexes: set[int]) -> None:
            self.enqueue_playlist_selection(listing, indexes)
            self.refresh_queue()

        picker = PlaylistPicker(self, listing, on_confirm=on_confirm)
        self._playlist_picker = picker

    def enqueue_playlist_selection(self, listing, indexes: set[int] | list[int]) -> list:
        from frameforge.download.playlist import enqueue_selected

        return enqueue_selected(
            self.repo,
            listing,
            indexes,
            format_preference=self._default_format(),
            upscale=self._default_upscale(),
        )

    def import_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Import URL list",
            filetypes=[("Text/Markdown", "*.txt *.md"), ("All", "*.*")],
        )
        if not path:
            return
        preview = preview_import(path, self.repo)
        msg = (
            f"New URLs: {preview.new_count}\n"
            f"Duplicates skipped: {preview.skipped_dupe_count}\n\n"
            "Add to queue only? (downloads will not start until you press Download)"
        )
        if not messagebox.askyesno("Bulk import", msg):
            return
        confirm_add(
            preview,
            self.repo,
            format_preference=self._default_format(),
            upscale=self._default_upscale(),
        )
        self.refresh_queue()

    def authenticate_selected_job(self) -> None:
        """Open Authenticate site… prefilled from the selected failed job (user-triggered)."""
        ids = self._selected_job_ids()
        prefill = None
        if ids:
            try:
                prefill = self.repo.get(ids[0]).url
            except Exception:  # noqa: BLE001
                prefill = None
        self.authenticate_site(prefill=prefill)

    def import_browser_selected_job(self) -> None:
        """Error-panel action: import cookies from browser for the selected auth-failed job."""
        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select a job first")
            return
        job = self.repo.get(sorted(ids)[0])
        result = self.import_cookies_from_browser_for_site(job.url, browser="firefox")
        if result.ok:
            messagebox.showinfo("FrameForge", result.message)
            return
        messagebox.showerror("FrameForge", result.message)
        self.authenticate_site(prefill=job.url)

    def import_cookies_from_browser_for_site(
        self,
        url_or_domain: str,
        *,
        browser: str = "firefox",
    ):
        from frameforge.download.browser_import import import_cookies_from_browser

        runner = getattr(self, "_browser_cookie_runner", None)
        return import_cookies_from_browser(
            url_or_domain,
            browser=browser,
            runner=runner,
        )

    def authenticate_site(self, prefill: str | None = None) -> None:
        from frameforge.download import cookies as cookie_mod

        win = ctk.CTkToplevel(self)
        win.title("Authenticate site")
        win.geometry("560x460")
        ctk.CTkLabel(
            win,
            text=(
                "Authenticate this site (one user-triggered path — no auto-open loops)\n\n"
                "Preferred: Import from browser (Firefox first). Chromium may fail while the\n"
                "browser is open (App-Bound Encryption) — then use Open browser + cookies.txt.\n\n"
                "If cookies already exist for the domain, Open browser is skipped (smart skip). "
                "Import again to replace stale cookies, then retry the failed job."
            ),
            justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 8))
        entry = ctk.CTkEntry(win, placeholder_text="https://example.com/ or example.com")
        entry.pack(fill="x", padx=16, pady=4)
        if prefill:
            entry.insert(0, prefill)
        status = ctk.CTkLabel(win, text="", anchor="w")
        status.pack(fill="x", padx=16, pady=4)

        def do_open() -> None:
            raw = entry.get().strip()
            if not raw:
                return
            try:
                domain = cookie_mod.normalize_domain(raw)
            except ValueError as exc:
                messagebox.showerror("FrameForge", str(exc))
                return
            if cookie_mod.should_skip_auth_prompt(domain) and cookie_mod.has_cookies(domain):
                status.configure(
                    text=f"Cookies already exist for {domain} — skipping browser open. Import to replace."
                )
                return
            cookie_mod.open_site_for_login(raw)
            status.configure(
                text=f"Opened browser for {domain}. After login, export cookies.txt and Import."
            )

        def do_import() -> None:
            raw = entry.get().strip()
            if not raw:
                messagebox.showerror("FrameForge", "Enter domain/URL first")
                return
            try:
                domain = cookie_mod.normalize_domain(raw)
            except ValueError as exc:
                messagebox.showerror("FrameForge", str(exc))
                return
            path = filedialog.askopenfilename(
                title="Import Netscape cookies.txt",
                filetypes=[("Cookie files", "*.txt"), ("All", "*.*")],
            )
            if not path:
                return
            try:
                dest = cookie_mod.import_netscape_cookies(domain, Path(path))
            except ValueError as exc:
                messagebox.showerror("FrameForge", str(exc))
                return
            status.configure(text=f"Saved cookies to {dest}")

        def do_import_browser() -> None:
            raw = entry.get().strip()
            if not raw:
                messagebox.showerror("FrameForge", "Enter domain/URL first")
                return
            browser = (browser_var.get() or "firefox").strip().lower()
            result = self.import_cookies_from_browser_for_site(raw, browser=browser)
            if result.ok:
                status.configure(text=result.message)
            else:
                messagebox.showerror("FrameForge", result.message)
                status.configure(
                    text="Browser import failed — use Open browser + Import cookies.txt."
                )

        from frameforge.download.browser_import import BROWSER_PREFERENCE

        browser_row = ctk.CTkFrame(win, fg_color="transparent")
        browser_row.pack(fill="x", padx=16, pady=(8, 0))
        ctk.CTkLabel(browser_row, text="Browser").pack(side="left", padx=(0, 8))
        browser_var = tk.StringVar(value="firefox")
        self._auth_browser_menu = ctk.CTkOptionMenu(
            browser_row,
            values=list(BROWSER_PREFERENCE),
            variable=browser_var,
            width=140,
        )
        self._auth_browser_menu.pack(side="left")
        self._auth_import_browser_btn = ctk.CTkButton(
            browser_row,
            text="Import from browser",
            command=do_import_browser,
        )
        self._auth_import_browser_btn.pack(side="left", padx=(8, 0))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(btn_row, text="Open browser", command=do_open).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Import cookies.txt", command=do_import).pack(side="left")

    def open_settings(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("420x280")
        ctk.CTkLabel(win, text="Format preference").pack(anchor="w", padx=16, pady=(16, 4))
        fmt = ctk.CTkEntry(win)
        fmt.insert(0, self._default_format())
        fmt.pack(fill="x", padx=16)
        upscale_var = tk.BooleanVar(value=self._default_upscale())
        ctk.CTkCheckBox(win, text="Upscale after download", variable=upscale_var).pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        tray_var = tk.BooleanVar(value=self._close_to_tray_enabled())
        ctk.CTkCheckBox(
            win,
            text="Close to system tray (window X hides; Quit still asks if work is running)",
            variable=tray_var,
        ).pack(anchor="w", padx=16, pady=8)

        def save() -> None:
            self.repo.set_setting("format_preference", fmt.get().strip() or "best")
            self.repo.set_setting("upscale_after_download", "1" if upscale_var.get() else "0")
            self.repo.set_setting("close_to_tray", "1" if tray_var.get() else "0")
            win.destroy()

        ctk.CTkButton(win, text="Save", command=save).pack(padx=16, pady=8)

    def download_selected(self) -> None:
        from frameforge.gui.actions import can_download

        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select one or more pending jobs first")
            return
        pending = [i for i in ids if can_download(self.repo.get(i))]
        if not pending:
            messagebox.showinfo("FrameForge", "No pending jobs in selection")
            return
        self.worker.request_download_ids(pending)
        self.refresh_queue()

    def download_all_pending(self) -> None:
        if self.repo.count_by_status("pending") == 0:
            messagebox.showinfo("FrameForge", "No pending jobs")
            return
        self.worker.request_download_all()
        self.refresh_queue()

    def set_format_selected(self) -> None:
        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select one or more jobs first")
            return
        self._open_format_picker(ids)

    def apply_format_to_jobs(self, job_ids: list[int], preference: str) -> None:
        from frameforge.download.formats import FORMAT_PRESETS

        value = FORMAT_PRESETS.get(preference, preference)
        for jid in job_ids:
            self.repo.set_format_preference(int(jid), value)
        self.refresh_queue()

    def _open_format_picker(self, job_ids: list[int]) -> None:
        from frameforge.download.formats import PRESET_LABELS, label_for_preference

        win = ctk.CTkToplevel(self)
        win.title("Set format")
        win.geometry("360x180")
        current = "Best"
        try:
            current = label_for_preference(self.repo.get(job_ids[0]).format_preference)
        except Exception:  # noqa: BLE001
            pass
        ctk.CTkLabel(win, text="Format for selected job(s)").pack(anchor="w", padx=16, pady=(16, 8))
        var = tk.StringVar(value=current if current in PRESET_LABELS else "Best")
        menu = ctk.CTkOptionMenu(win, values=list(PRESET_LABELS), variable=var)
        menu.pack(fill="x", padx=16)

        def save() -> None:
            self.apply_format_to_jobs(job_ids, var.get())
            win.destroy()

        ctk.CTkButton(win, text="Apply", command=save).pack(pady=16)
        self._format_picker = win

    def upscale_selected(self) -> None:
        from frameforge.gui.actions import can_upscale

        ids = self._selected_job_ids()
        eligible = [i for i in ids if can_upscale(self.repo.get(i))]
        if not eligible:
            messagebox.showinfo(
                "FrameForge",
                "Select one or more completed downloads with a local file first",
            )
            return
        try:
            queued = self.worker.request_upscale_ids(eligible)
        except ValueError as exc:
            messagebox.showerror("FrameForge", str(exc))
            return
        messagebox.showinfo(
            "FrameForge",
            f"Queued {len(queued)} job(s) for 2× upscale (runs one at a time).",
        )
        self.refresh_queue()

    def select_recommended(self) -> None:
        """Multi-select all completed jobs currently recommended for 2× upscale."""
        self.refresh_queue()
        ids = self.queue_list.recommended_ids
        if not ids:
            messagebox.showinfo("FrameForge", "No ≤720p completed jobs recommended right now")
            return
        self.queue_list.set_selected(ids)
        self._selected_ids = set(ids)

    def stop_worker(self) -> None:
        self.worker.disarm()
        self.refresh_queue()

    def cancel_selected(self) -> None:
        from frameforge.gui.actions import can_cancel

        ids = self._selected_job_ids()
        if not ids:
            return
        for job_id in ids:
            if can_cancel(self.repo.get(job_id)):
                self.worker.cancel_job(job_id)
        self.refresh_queue()

    def pause_selected(self) -> None:
        from frameforge.gui.actions import can_pause

        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select a downloading job to pause")
            return
        paused_any = False
        for job_id in ids:
            if can_pause(self.repo.get(job_id)):
                self.worker.pause_job(job_id)
                paused_any = True
        if not paused_any:
            messagebox.showinfo("FrameForge", "Pause is only available while a job is downloading or upscaling")
        self.refresh_queue()

    def resume_selected(self) -> None:
        from frameforge.gui.actions import can_resume

        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select a paused job to resume")
            return
        resumed_any = False
        for job_id in ids:
            if can_resume(self.repo.get(job_id)):
                self.worker.resume_job(job_id)
                resumed_any = True
        if not resumed_any:
            messagebox.showinfo("FrameForge", "Resume is only available for paused jobs")
        self.refresh_queue()

    def retry_failed(self) -> None:
        for job in self.repo.list_jobs("failed"):
            self.repo.update_status(job.id, "pending", error=None, progress=0)
        self.refresh_queue()

    def retry_history_selected(self) -> None:
        ids = sorted(self.history_list.selected_ids)
        n = 0
        for jid in ids:
            job = self.repo.get(jid)
            if job.status == "failed":
                self.repo.update_status(job.id, "pending", error=None, progress=0)
                self.repo.merge_options(job.id, {"history_hidden": False})
                n += 1
        if n == 0:
            messagebox.showinfo("FrameForge", "Select one or more failed history jobs to retry")
            return
        self.refresh_queue()

    def hide_history_selected(self) -> None:
        ids = sorted(self.history_list.selected_ids)
        if not ids:
            messagebox.showinfo("FrameForge", "Select history rows to hide")
            return
        self.repo.hide_from_history(ids)
        self.refresh_history()

    def refresh_history(self) -> None:
        filt = "All"
        try:
            filt = str(self.history_filter.get())
        except Exception:  # noqa: BLE001
            pass
        status = None
        if filt == "Completed":
            status = "completed"
        elif filt == "Failed":
            status = "failed"
        search = ""
        try:
            search = self.history_search.get().strip()
        except Exception:  # noqa: BLE001
            pass
        jobs = self.repo.list_history(status=status, search=search or None)
        self.history_list.update_jobs(jobs)

    def focus_job(self, job_id: int) -> bool:
        """Select *job_id* in Queue/History if it still exists. Returns True if found."""
        try:
            job = self.repo.get(int(job_id))
        except KeyError:
            return False
        self.queue_list.set_selected({job.id})
        hist_ids = {j.id for j in self.repo.list_history()}
        if job.id in hist_ids:
            self.history_list.set_selected({job.id})
        self._selected_ids = {job.id}
        try:
            self.tabs.set("Queue")
        except Exception:  # noqa: BLE001
            pass
        self._update_error_panel()
        return True

    def refresh_thumbnails(self) -> None:
        from frameforge.download.thumbnails import list_thumbnail_jobs
        from PIL import Image

        jobs = list_thumbnail_jobs(self.repo)
        sig = tuple(f"{j.id}:{j.thumbnail_path}" for j in jobs)
        if sig == self._thumb_tab_sig and self._thumb_tab_widgets:
            return
        self._thumb_tab_sig = sig
        for w in self._thumb_tab_widgets:
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._thumb_tab_widgets = []
        jobs = list_thumbnail_jobs(self.repo)
        cols = 4
        for i, job in enumerate(jobs):
            path = job.thumbnail_path
            try:
                img = Image.open(path)
                img = img.convert("RGB")
                img.thumbnail((120, 90))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            except Exception:  # noqa: BLE001
                ctk_img = None
            btn = ctk.CTkButton(
                self.thumbs_frame,
                text=f"#{job.id}",
                image=ctk_img,
                compound="top",
                width=130,
                height=110,
                command=lambda jid=job.id: self.focus_job(jid),
            )
            r, c = divmod(i, cols)
            btn.grid(row=r, column=c, padx=6, pady=6, sticky="n")
            self._thumb_tab_widgets.append(btn)

    def bump_priority(self, delta: int) -> None:
        ids = self._selected_job_ids()
        if not ids:
            return
        for job_id in ids:
            job = self.repo.get(job_id)
            self.repo.set_priority(job_id, job.priority + delta)
        self.refresh_queue()

    def open_folder_selected(self) -> None:
        from frameforge.util.reveal import RevealError, open_job_folder

        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select a job with a local file first")
            return
        job = self.repo.get(sorted(ids)[0])
        try:
            open_job_folder(job, launch=True)
        except RevealError as exc:
            messagebox.showerror("FrameForge", str(exc))

    def reveal_file_selected(self) -> None:
        from frameforge.util.reveal import RevealError, reveal_job_file

        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select a job with a local file first")
            return
        job = self.repo.get(sorted(ids)[0])
        try:
            reveal_job_file(job, launch=True)
        except RevealError as exc:
            messagebox.showerror("FrameForge", str(exc))

    def refresh_queue(self) -> None:
        jobs = self.repo.list_jobs()
        self.queue_list.update_jobs(jobs)
        self.refresh_history()
        self.refresh_thumbnails()

        downloading = 0
        upscaling = 0
        active = None
        for job in jobs:
            if job.status == "downloading":
                downloading += 1
                active = job
            elif job.status == "upscaling":
                upscaling += 1
                if active is None:
                    active = job

        if active and active.status == "downloading":
            self.progress_bar.set(max(0.0, min(1.0, active.progress / 100.0)))
            opts = active.options()
            speed = opts.get("speed_str") or "—"
            eta = opts.get("eta_str") or "—"
            self.progress_label.configure(
                text=f"Downloading #{active.id} — {active.progress:.1f}% | {speed} | ETA {eta}"
            )
        elif active and active.status == "upscaling":
            self.progress_bar.set(max(0.0, min(1.0, active.progress / 100.0)))
            self.progress_label.configure(
                text=f"Upscaling #{active.id} (2×) — {active.progress:.1f}%"
            )
        else:
            paused_jobs = [j for j in jobs if j.status == "paused"]
            if paused_jobs and not self.worker.is_armed:
                p = paused_jobs[0]
                self.progress_bar.set(max(0.0, min(1.0, p.progress / 100.0)))
                self.progress_label.configure(
                    text=f"Paused #{p.id} — {p.progress:.1f}% (Resume to continue)"
                )
            elif not self.worker.is_armed:
                self.progress_bar.set(0)
                self.progress_label.configure(text="Idle — 0% | — | ETA —")
            else:
                self.progress_label.configure(text="Worker armed — waiting for next job…")

        if downloading > 1 or upscaling > 1 or (downloading + upscaling) > 1:
            self.seq_banner.configure(text="ERROR: more than one active stage")
        elif self.worker.is_armed:
            self.seq_banner.configure(
                text="Worker running — one download or upscale at a time (sequential)"
            )
        else:
            paused_n = sum(1 for j in jobs if j.status == "paused")
            if paused_n:
                self.seq_banner.configure(
                    text=(
                        f"{paused_n} paused job(s) — Resume to continue. "
                        "Downloads run one at a time — queue only until you press Download"
                    )
                )
            else:
                self.seq_banner.configure(
                    text="Downloads run one at a time — queue only until you press Download"
                )
        self._update_error_panel()

    def _tick(self) -> None:
        if self._shutting_down:
            return
        self.refresh_queue()
        if self.worker.wait_to_quit:
            from frameforge.gui.exit_policy import QUIT_NOW, classify_exit

            if classify_exit(self.repo, self.worker) == QUIT_NOW:
                self._finish_quit()
                return
        self.after(1000, self._tick)

    def shutdown(self) -> None:
        try:
            self.tray.stop(timeout=3)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.worker.stop(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.repo.close()
        except Exception:  # noqa: BLE001
            pass


def create_app(**kwargs: Any) -> FrameForgeApp:
    return FrameForgeApp(**kwargs)
