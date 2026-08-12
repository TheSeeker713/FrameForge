"""FrameForge CustomTkinter application."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
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
    def __init__(self, repo: JobRepository | None = None, *, start_worker: bool = True):
        super().__init__()
        ensure_output_tree()
        self.title("FrameForge")
        self.geometry("980x640")
        self.repo = repo or JobRepository(db_path())
        self.worker: SequentialWorker | None = None
        self._refresh_job = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkLabel(self, text="FrameForge", font=ctk.CTkFont(size=28, weight="bold"))
        header.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")

        self.seq_banner = ctk.CTkLabel(
            self,
            text="Downloads run one at a time (sequential queue)",
            text_color="#9ad0ff",
        )
        self.seq_banner.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(row, placeholder_text="Paste video URL…")
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.add_btn = ctk.CTkButton(row, text="Add", width=90, command=self.add_url)
        self.add_btn.grid(row=0, column=1, padx=(0, 8))
        self.import_btn = ctk.CTkButton(row, text="Import TXT/MD", width=120, command=self.import_file)
        self.import_btn.grid(row=0, column=2, padx=(0, 8))
        self.settings_btn = ctk.CTkButton(row, text="Settings", width=90, command=self.open_settings)
        self.settings_btn.grid(row=0, column=3)

        self.queue_box = ctk.CTkTextbox(self, wrap="none")
        self.queue_box.grid(row=3, column=0, padx=16, pady=8, sticky="nsew")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=4, column=0, padx=16, pady=(4, 16), sticky="ew")
        self.cancel_btn = ctk.CTkButton(controls, text="Cancel selected", command=self.cancel_selected)
        self.cancel_btn.pack(side="left", padx=(0, 8))
        self.retry_btn = ctk.CTkButton(controls, text="Retry failed", command=self.retry_failed)
        self.retry_btn.pack(side="left", padx=(0, 8))
        self.prio_up_btn = ctk.CTkButton(controls, text="Priority +", command=lambda: self.bump_priority(1))
        self.prio_up_btn.pack(side="left", padx=(0, 8))
        self.prio_down_btn = ctk.CTkButton(controls, text="Priority -", command=lambda: self.bump_priority(-1))
        self.prio_down_btn.pack(side="left", padx=(0, 8))
        self.refresh_btn = ctk.CTkButton(controls, text="Refresh", command=self.refresh_queue)
        self.refresh_btn.pack(side="left")

        self.bind("<Control-v>", self._paste_focus)
        self.bind("<Control-Return>", lambda e: self.add_url())

        if start_worker:
            self.worker = build_worker(self.repo)
            self.worker.start()
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
            f"Duplicates skipped: {preview.skipped_dupe_count}\n\nAdd to queue?"
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

    def _selected_job_id(self) -> int | None:
        try:
            line = self.queue_box.get("insert linestart", "insert lineend").strip()
            if not line or line.startswith("id"):
                return None
            return int(line.split("|", 1)[0].strip())
        except Exception:
            return None

    def cancel_selected(self) -> None:
        job_id = self._selected_job_id()
        if job_id is None:
            return
        self.repo.cancel(job_id)
        self.refresh_queue()

    def retry_failed(self) -> None:
        for job in self.repo.list_jobs("failed"):
            self.repo.update_status(job.id, "pending", error=None, progress=0)
        self.refresh_queue()

    def bump_priority(self, delta: int) -> None:
        job_id = self._selected_job_id()
        if job_id is None:
            return
        job = self.repo.get(job_id)
        self.repo.set_priority(job_id, job.priority + delta)
        self.refresh_queue()

    def refresh_queue(self) -> None:
        lines = ["id | status | progress | priority | title/url"]
        downloading = 0
        for job in self.repo.list_jobs():
            if job.status == "downloading":
                downloading += 1
            title = job.title or job.url
            lines.append(
                f"{job.id} | {job.status} | {job.progress:.1f}% | {job.priority} | {title}"
            )
        self.queue_box.delete("1.0", "end")
        self.queue_box.insert("1.0", "\n".join(lines))
        if downloading > 1:
            self.seq_banner.configure(text="ERROR: more than one download active")
        else:
            self.seq_banner.configure(
                text="Downloads run one at a time (sequential queue)"
            )

    def _tick(self) -> None:
        self.refresh_queue()
        self.after(1000, self._tick)

    def shutdown(self) -> None:
        if self.worker:
            self.worker.stop(timeout=5)
        self.repo.close()


def create_app(**kwargs: Any) -> FrameForgeApp:
    return FrameForgeApp(**kwargs)
