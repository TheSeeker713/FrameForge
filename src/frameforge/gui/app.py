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
    def __init__(self, repo: JobRepository | None = None, *, start_worker: bool = False):
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

        self.queue_list = QueueList(
            self,
            on_selection_changed=self._on_selection_changed,
            label_text="Queue",
        )
        self.queue_list.grid(row=5, column=0, padx=16, pady=8, sticky="nsew")
        # Back-compat alias for older tests expecting queue_box text
        self.queue_box = self.queue_list

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=6, column=0, padx=16, pady=(4, 16), sticky="ew")
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
        self.refresh_btn = ctk.CTkButton(controls, text="Refresh", command=self.refresh_queue)
        self.refresh_btn.pack(side="left")

        self.bind("<Control-v>", self._paste_focus)
        self.bind("<Control-Return>", lambda e: self.add_url())

        if start_worker:
            self.worker.request_download_all()

        self.refresh_queue()
        self.after(1000, self._tick)

    def _on_selection_changed(self, ids: set[int]) -> None:
        self._selected_ids = set(ids)

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
        self.repo.enqueue(
            url,
            format_preference=self._default_format(),
            upscale=self._default_upscale(),
        )
        self.url_entry.delete(0, "end")
        self.refresh_queue()

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

    def authenticate_site(self) -> None:
        from frameforge.download import cookies as cookie_mod

        win = ctk.CTkToplevel(self)
        win.title("Authenticate site")
        win.geometry("520x320")
        ctk.CTkLabel(
            win,
            text=(
                "1) Enter a site URL or domain\n"
                "2) Open browser and log in / accept gates\n"
                "3) Export Netscape cookies.txt (browser extension)\n"
                "4) Import that file here\n\n"
                "If cookies already exist for the domain, re-auth is skipped unless you import again."
            ),
            justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 8))
        entry = ctk.CTkEntry(win, placeholder_text="https://example.com/ or example.com")
        entry.pack(fill="x", padx=16, pady=4)
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
            dest = cookie_mod.import_netscape_cookies(domain, Path(path))
            status.configure(text=f"Saved cookies to {dest}")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(btn_row, text="Open browser", command=do_open).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Import cookies.txt", command=do_import).pack(side="left")

    def open_settings(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("420x220")
        ctk.CTkLabel(win, text="Format preference").pack(anchor="w", padx=16, pady=(16, 4))
        fmt = ctk.CTkEntry(win)
        fmt.insert(0, self._default_format())
        fmt.pack(fill="x", padx=16)
        upscale_var = tk.BooleanVar(value=self._default_upscale())
        ctk.CTkCheckBox(win, text="Upscale after download", variable=upscale_var).pack(
            anchor="w", padx=16, pady=16
        )

        def save() -> None:
            self.repo.set_setting("format_preference", fmt.get().strip() or "best")
            self.repo.set_setting("upscale_after_download", "1" if upscale_var.get() else "0")
            win.destroy()

        ctk.CTkButton(win, text="Save", command=save).pack(padx=16, pady=8)

    def _selected_job_ids(self) -> list[int]:
        return sorted(self._selected_ids or self.queue_list.selected_ids)

    def download_selected(self) -> None:
        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo("FrameForge", "Select one or more pending jobs first")
            return
        pending = [i for i in ids if self.repo.get(i).status == "pending"]
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

    def upscale_selected(self) -> None:
        ids = self._selected_job_ids()
        if not ids:
            messagebox.showinfo(
                "FrameForge",
                "Select one or more completed downloads with a local file first",
            )
            return
        try:
            queued = self.worker.request_upscale_ids(ids)
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
        ids = self._selected_job_ids()
        if not ids:
            return
        for job_id in ids:
            self.worker.cancel_job(job_id)
        self.refresh_queue()

    def retry_failed(self) -> None:
        for job in self.repo.list_jobs("failed"):
            self.repo.update_status(job.id, "pending", error=None, progress=0)
        self.refresh_queue()

    def bump_priority(self, delta: int) -> None:
        ids = self._selected_job_ids()
        if not ids:
            return
        for job_id in ids:
            job = self.repo.get(job_id)
            self.repo.set_priority(job_id, job.priority + delta)
        self.refresh_queue()

    def refresh_queue(self) -> None:
        jobs = self.repo.list_jobs()
        self.queue_list.update_jobs(jobs)

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
            self.seq_banner.configure(
                text="Downloads run one at a time — queue only until you press Download"
            )

    def _tick(self) -> None:
        self.refresh_queue()
        self.after(1000, self._tick)

    def shutdown(self) -> None:
        self.worker.stop(timeout=5)
        self.repo.close()


def create_app(**kwargs: Any) -> FrameForgeApp:
    return FrameForgeApp(**kwargs)
