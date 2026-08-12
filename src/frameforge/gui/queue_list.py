"""Selectable queue list that preserves scroll position across refreshes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from frameforge.db.repository import Job


class QueueList(ctk.CTkScrollableFrame):
    """Multi-select job list with in-place row updates (no jump-to-top wipe)."""

    def __init__(
        self,
        master: Any,
        *,
        on_selection_changed: Callable[[set[int]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_selection_changed = on_selection_changed
        self._rows: dict[int, dict[str, Any]] = {}
        self._selected: set[int] = set()
        self._order: list[int] = []

    @property
    def selected_ids(self) -> set[int]:
        return set(self._selected)

    def set_selected(self, ids: set[int]) -> None:
        self._selected = set(ids)
        for job_id, row in self._rows.items():
            var: ctk.BooleanVar = row["var"]
            var.set(job_id in self._selected)

    def scroll_fraction(self) -> float:
        try:
            return float(self._parent_canvas.yview()[0])
        except Exception:
            return 0.0

    def restore_scroll(self, frac: float) -> None:
        try:
            self._parent_canvas.yview_moveto(max(0.0, min(1.0, frac)))
        except Exception:
            pass

    def _toggle(self, job_id: int) -> None:
        var = self._rows[job_id]["var"]
        if var.get():
            self._selected.add(job_id)
        else:
            self._selected.discard(job_id)
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_ids)

    def _make_row(self, job: Job) -> dict[str, Any]:
        frame = ctk.CTkFrame(self, fg_color=("gray90", "gray20"))
        var = ctk.BooleanVar(value=job.id in self._selected)
        chk = ctk.CTkCheckBox(
            frame,
            text="",
            width=24,
            variable=var,
            command=lambda jid=job.id: self._toggle(jid),
        )
        chk.pack(side="left", padx=(6, 4), pady=4)
        label = ctk.CTkLabel(frame, anchor="w", justify="left")
        label.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        return {"frame": frame, "var": var, "label": label, "chk": chk}

    def _format(self, job: Job) -> str:
        title = (job.title or job.url or "")[:60]
        err = f"  ERR:{job.error[:40]}" if job.error else ""
        return (
            f"#{job.id}  [{job.status}]  {job.progress:.1f}%  "
            f"prio={job.priority}  {title}{err}"
        )

    def update_jobs(self, jobs: list[Job]) -> None:
        """Refresh rows without resetting scroll or wiping selection unexpectedly."""
        frac = self.scroll_fraction()
        new_ids = [j.id for j in jobs]
        new_set = set(new_ids)

        # Remove rows for deleted jobs
        for job_id in list(self._rows):
            if job_id not in new_set:
                self._rows[job_id]["frame"].destroy()
                del self._rows[job_id]
                self._selected.discard(job_id)

        # Create / update in order
        for job in jobs:
            if job.id not in self._rows:
                self._rows[job.id] = self._make_row(job)
            row = self._rows[job.id]
            row["label"].configure(text=self._format(job))
            row["var"].set(job.id in self._selected)
            row["frame"].pack_forget()

        for job_id in new_ids:
            self._rows[job_id]["frame"].pack(fill="x", padx=2, pady=2)

        self._order = new_ids
        self.after(1, lambda: self.restore_scroll(frac))
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_ids)
