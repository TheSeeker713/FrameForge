"""Single-instance Flet dialog stack.

v0.5.0 left Authenticate (and several other AlertDialogs) on ``page.show_dialog``
without a matching ``pop_dialog``, so X / Cancel / barrier clicks did nothing.
Every modal goes through DialogHost.open / close.
"""

from __future__ import annotations

from typing import Any

import flet as ft


class DialogHost:
    """At most one AlertDialog. close() is idempotent."""

    def __init__(self, ui: Any) -> None:
        self.ui = ui
        self.current: ft.AlertDialog | None = None
        self.kind: str | None = None
        self.close_count = 0
        self.open_kinds: list[str] = []
        self._closing = False

    def close(self, _e: Any = None) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            dlg = self.current
            kind = self.kind
            self.current = None
            self.kind = None
            self.close_count += 1
            self._clear_kind_flag(kind)
            if dlg is not None:
                dlg.open = False
            page = getattr(self.ui, "page", None)
            if page is not None and not getattr(self.ui, "_exiting", False):
                try:
                    page.pop_dialog()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    page.update()
                except Exception:  # noqa: BLE001
                    pass
            elif page is not None:
                try:
                    page.pop_dialog()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self._closing = False

    def open(self, kind: str, dialog: ft.AlertDialog) -> ft.AlertDialog:
        if self.current is not None and self.kind == kind:
            if kind == "settings":
                self.ui.settings_focus_count += 1
            page = getattr(self.ui, "page", None)
            if page is not None:
                try:
                    page.show_dialog(self.current)
                    page.update()
                except Exception:  # noqa: BLE001
                    pass
            return self.current
        if self.current is not None:
            self.close()
        if kind != "quit":
            from frameforge.ui_flet.components.modals import wire_closable

            wire_closable(dialog, self.close)
        self.current = dialog
        self.kind = kind
        self.open_kinds.append(kind)
        self._set_kind_flag(kind)
        page = getattr(self.ui, "page", None)
        if page is not None:
            page.show_dialog(dialog)
            try:
                page.update()
            except Exception:  # noqa: BLE001
                pass
        return dialog

    def _set_kind_flag(self, kind: str | None) -> None:
        if kind == "settings":
            self.ui.bridge.settings_open = True
        elif kind == "auth":
            self.ui.auth_open = True
        elif kind == "format":
            self.ui.format_open = True
        elif kind == "bulk":
            self.ui.bulk_open = True
        elif kind == "playlist":
            self.ui.playlist_open = True

    def _clear_kind_flag(self, kind: str | None) -> None:
        if kind == "settings":
            self.ui.bridge.settings_open = False
        elif kind == "auth":
            self.ui.auth_open = False
        elif kind == "format":
            self.ui.format_open = False
        elif kind == "bulk":
            self.ui.bulk_open = False
        elif kind == "playlist":
            self.ui.playlist_open = False
