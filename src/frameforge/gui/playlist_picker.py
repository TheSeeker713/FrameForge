"""Modal playlist subset picker (checkboxes → enqueue pending only)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from frameforge.download.playlist import PlaylistListing


class PlaylistPicker(ctk.CTkToplevel):
    """Select playlist entries. Confirm calls *on_confirm(indexes)* then destroys."""

    def __init__(
        self,
        master: Any,
        listing: PlaylistListing,
        *,
        on_confirm: Callable[[set[int]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, **kwargs)
        self.listing = listing
        self.on_confirm = on_confirm
        self._vars: dict[int, Any] = {}
        title = listing.title or "Playlist"
        n = len(listing.entries)
        extra = f" (showing {n} of {listing.total_count})" if listing.truncated else f" ({n})"
        self.title("Playlist")
        self.geometry("640x480")
        ctk.CTkLabel(self, text=f"{title}{extra}", anchor="w").pack(
            fill="x", padx=16, pady=(16, 8)
        )
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(btn_row, text="Select all", width=110, command=self.select_all).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(btn_row, text="Select none", width=110, command=self.select_none).pack(
            side="left"
        )
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="Entries")
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=8)
        for entry in listing.entries:
            var = ctk.BooleanVar(value=True)
            self._vars[entry.index] = var
            label = f"{entry.index}. {entry.title or entry.url}"
            ctk.CTkCheckBox(self.list_frame, text=label[:90], variable=var).pack(
                anchor="w", padx=4, pady=2
            )
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(foot, text="Enqueue selected", command=self.confirm).pack(side="right")
        ctk.CTkButton(foot, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))

    def selected_indexes(self) -> set[int]:
        return {idx for idx, var in self._vars.items() if bool(var.get())}

    def select_all(self) -> None:
        for var in self._vars.values():
            var.set(True)

    def select_none(self) -> None:
        for var in self._vars.values():
            var.set(False)

    def confirm(self) -> None:
        chosen = self.selected_indexes()
        cb = self.on_confirm
        self.destroy()
        if cb:
            cb(chosen)
