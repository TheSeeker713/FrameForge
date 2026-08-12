"""FrameForge CustomTkinter application."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import confirm_add, preview_import
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

        # Temporary textbox queue — replaced in T1.3 with selectable rows
        self.queue_box = ctk.CTkTextbox(self, wrap="none")
        self.queue_box.grid(row=5, column=0, padx=16, pady=8, sticky="nsew")

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
        """Placeholder until T1.4 cookie module is wired."""
        messagebox.showinfo(
            "FrameForge",
            "Cookie authentication arrives in Tier 1.4. "
            "Cookies will live under Downloads\\FrameForge\\cookies\\.",
        )

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
        if self._selected_ids:
            return sorted(self._selected_ids)
        try:
            line = self.queue_box.get("insert linestart", "insert lineend").strip()
            if not line or line.startswith("id"):
                return []
            return [int(line.lstrip("* ").split("|", 1)[0].strip())]
        except Exception:
            return []

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

    def stop_worker(self) -> None:
        self.worker.disarm()
        self.refresh_queue()

    def cancel_selected(self) -> None:
        ids = self._selected_job_ids()
        if not ids:
            return
        for job_id in ids:
            self.repo.cancel(job_id)
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
        lines = ["id | status | progress | priority | title/url"]
        downloading = 0
        active = None
        for job in self.repo.list_jobs():
            if job.status == "downloading":
                downloading += 1
                active = job
            title = job.title or job.url
            mark = "*" if job.id in self._selected_ids else " "
            lines.append(
                f"{mark}{job.id} | {job.status} | {job.progress:.1f}% | {job.priority} | {title}"
            )
        try:
            y = self.queue_box.yview()
        except Exception:
            y = (0.0, 1.0)
        self.queue_box.delete("1.0", "end")
        self.queue_box.insert("1.0", "\n".join(lines))
        try:
            self.queue_box.yview_moveto(y[0])
        except Exception:
            pass

        if active:
            self.progress_bar.set(max(0.0, min(1.0, active.progress / 100.0)))
            opts = active.options()
            speed = opts.get("speed_str") or "—"
            eta = opts.get("eta_str") or "—"
            self.progress_label.configure(
                text=f"Downloading #{active.id} — {active.progress:.1f}% | {speed} | ETA {eta}"
            )
        elif not self.worker.is_armed:
            self.progress_bar.set(0)
            self.progress_label.configure(text="Idle — 0% | — | ETA —")
        else:
            self.progress_label.configure(text="Worker armed — waiting for next job…")

        if downloading > 1:
            self.seq_banner.configure(text="ERROR: more than one download active")
        elif self.worker.is_armed:
            self.seq_banner.configure(
                text="Worker running — downloads one at a time (sequential)"
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
