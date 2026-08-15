"""Headless Flet page stand-in for dialog / shutdown tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list[Any] = []
        self.dialog: Any | None = None
        self.popped = 0
        self.updates = 0
        self.overlay: list[Any] = []
        self.services: list[Any] = []
        self.window = SimpleNamespace(
            prevent_close=False,
            on_event=None,
            bgcolor=None,
            opacity=1.0,
            shadow=True,
            title_bar_hidden=False,
            frameless=False,
            visible=True,
            ignore_mouse_events=False,
            width=None,
            height=None,
            min_width=None,
            min_height=None,
        )
        self.on_disconnect = None
        self.on_keyboard_event = None
        self.on_close = None
        self.title = None
        self.bgcolor = None
        self.theme_mode = None
        self.padding = None
        self.theme = None
        self.added: list[Any] = []
        self.clipboard: str | None = None

    def set_clipboard(self, text: str) -> None:
        self.clipboard = text

    def show_dialog(self, dialog: Any) -> None:
        dialog.open = True
        self.dialog = dialog
        self.dialogs = [dialog]

    def pop_dialog(self) -> Any | None:
        self.popped += 1
        dlg = self.dialog
        self.dialog = None
        self.dialogs = []
        if dlg is not None:
            dlg.open = False
        return dlg

    def update(self) -> None:
        self.updates += 1

    def add(self, *controls: Any) -> None:
        self.added.extend(controls)

    def run_task(self, fn: Any, *args: Any, **kwargs: Any) -> None:
        return None
