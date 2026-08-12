"""Selectable queue list that preserves scroll position across refreshes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image

from frameforge.db.repository import Job


# Accent for ≤720p recommended upscale rows
_RECOMMENDED_FG = ("#d8f5d0", "#1f3d2a")
_NORMAL_FG = ("gray90", "gray20")
_BLOCKED_FG = ("#f5d0d0", "#3d1f1f")
_PAUSED_FG = ("#f5e6c8", "#3d3420")
_THUMB_SIZE = (48, 36)


class QueueList(ctk.CTkScrollableFrame):
    """Multi-select job list with in-place row updates (no jump-to-top wipe)."""

    def __init__(
        self,
        master: Any,
        *,
        on_selection_changed: Callable[[set[int]], None] | None = None,
        show_timestamps: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_selection_changed = on_selection_changed
        self._rows: dict[int, dict[str, Any]] = {}
        self._selected: set[int] = set()
        self._order: list[int] = []
        self._recommended_ids: set[int] = set()
        self._show_timestamps = bool(show_timestamps)
        self._thumb_cache: dict[str, Any] = {}
        self._placeholder_thumb = self._make_placeholder()

    @property
    def selected_ids(self) -> set[int]:
        return set(self._selected)

    @property
    def recommended_ids(self) -> set[int]:
        return set(self._recommended_ids)

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

    def _row_colors(self, job: Job) -> tuple[str, str] | str:
        if job.status == "paused":
            return _PAUSED_FG
        if job.upscale_recommended and job.status == "completed":
            return _RECOMMENDED_FG
        if job.upscale_blocked:
            return _BLOCKED_FG
        return _NORMAL_FG

    def _make_row(self, job: Job) -> dict[str, Any]:
        frame = ctk.CTkFrame(self, fg_color=self._row_colors(job))
        var = ctk.BooleanVar(value=job.id in self._selected)
        chk = ctk.CTkCheckBox(
            frame,
            text="",
            width=24,
            variable=var,
            command=lambda jid=job.id: self._toggle(jid),
        )
        chk.pack(side="left", padx=(6, 4), pady=4)
        thumb = ctk.CTkLabel(frame, text="", width=_THUMB_SIZE[0], height=_THUMB_SIZE[1])
        thumb.pack(side="left", padx=(0, 6), pady=4)
        badge = ctk.CTkLabel(frame, text="", width=110, anchor="w")
        badge.pack(side="left", padx=(0, 4))
        label = ctk.CTkLabel(frame, anchor="w", justify="left")
        label.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        return {
            "frame": frame,
            "var": var,
            "label": label,
            "chk": chk,
            "badge": badge,
            "thumb": thumb,
            "thumb_path": None,
        }

    def _make_placeholder(self) -> Any:
        img = Image.new("RGB", _THUMB_SIZE, color=(48, 48, 52))
        return ctk.CTkImage(light_image=img, dark_image=img, size=_THUMB_SIZE)

    def _thumb_image(self, path: str | None) -> Any:
        if not path:
            return self._placeholder_thumb
        cached = self._thumb_cache.get(path)
        if cached is not None:
            return cached
        try:
            img = Image.open(path)
            img = img.convert("RGB")
            img.thumbnail(_THUMB_SIZE)
            canvas = Image.new("RGB", _THUMB_SIZE, color=(48, 48, 52))
            x = (_THUMB_SIZE[0] - img.size[0]) // 2
            y = (_THUMB_SIZE[1] - img.size[1]) // 2
            canvas.paste(img, (x, y))
            ctk_img = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=_THUMB_SIZE)
            self._thumb_cache[path] = ctk_img
            return ctk_img
        except Exception:  # noqa: BLE001
            return self._placeholder_thumb

    def _apply_thumb(self, row: dict[str, Any], job: Job) -> None:
        path = job.thumbnail_path
        if path and not Path(path).is_file():
            path = None
        if row.get("thumb_path") == path:
            return
        row["thumb"].configure(image=self._thumb_image(path))
        row["thumb_path"] = path

    def _format(self, job: Job) -> str:
        title = (job.title or job.url or "")[:52]
        site = f"  [{job.extractor}]" if job.extractor else ""
        res = ""
        if job.source_height:
            res = f"  {job.source_width or '?'}x{job.source_height}"
        err = f"  ERR:{job.error[:36]}" if job.error else ""
        ts = ""
        if self._show_timestamps:
            ts = f"  {job.finished_at or job.updated_at or ''}"
        return (
            f"#{job.id}  [{job.status}]  {job.progress:.1f}%  "
            f"prio={job.priority}{site}{res}  {title}{err}{ts}"
        )

    def _badge_text(self, job: Job) -> str:
        if job.status == "paused":
            return "PAUSED"
        if job.upscale_recommended and job.status == "completed":
            return "RECOMMENDED 2×"
        if job.upscale_blocked:
            return "BLOCKED 4K+"
        if job.playlist_badge:
            return job.playlist_badge
        return ""

    def update_jobs(self, jobs: list[Job]) -> None:
        """Refresh rows without resetting scroll or wiping selection unexpectedly."""
        frac = self.scroll_fraction()
        new_ids = [j.id for j in jobs]
        new_set = set(new_ids)
        self._recommended_ids = {
            j.id for j in jobs if j.upscale_recommended and j.status == "completed"
        }

        for job_id in list(self._rows):
            if job_id not in new_set:
                self._rows[job_id]["frame"].destroy()
                del self._rows[job_id]
                self._selected.discard(job_id)

        for job in jobs:
            if job.id not in self._rows:
                self._rows[job.id] = self._make_row(job)
            row = self._rows[job.id]
            row["label"].configure(text=self._format(job))
            row["badge"].configure(text=self._badge_text(job))
            row["frame"].configure(fg_color=self._row_colors(job))
            row["var"].set(job.id in self._selected)
            self._apply_thumb(row, job)
            row["frame"].pack_forget()

        for job_id in new_ids:
            self._rows[job_id]["frame"].pack(fill="x", padx=2, pady=2)

        self._order = new_ids
        self.after(1, lambda: self.restore_scroll(frac))
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_ids)
