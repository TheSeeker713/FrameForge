"""Central keyboard shortcut registry (action id → key sequence → handler)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Tk event.state bits
_CTRL = 0x4
_ALT = 0x20000
_MOD1 = 0x8


@dataclass(frozen=True)
class Shortcut:
    action_id: str
    label: str
    sequence: str
    display: str


DEFAULT_SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut("focus_url", "Focus add URL", "<Control-l>", "Ctrl+L"),
    Shortcut("download_selected", "Download selected", "<Control-d>", "Ctrl+D"),
    Shortcut("download_all", "Download all pending", "<Control-Shift-D>", "Ctrl+Shift+D"),
    Shortcut("pause", "Pause", "<Control-p>", "Ctrl+P"),
    Shortcut("resume", "Resume", "<Control-Shift-P>", "Ctrl+Shift+P"),
    Shortcut("cancel_selected", "Cancel selected", "<Control-Shift-C>", "Ctrl+Shift+C"),
    Shortcut("upscale_selected", "Upscale selected", "<Control-u>", "Ctrl+U"),
    Shortcut("select_recommended", "Select recommended", "<Control-Shift-U>", "Ctrl+Shift+U"),
    Shortcut("convert_mp3", "Convert to MP3", "<Control-m>", "Ctrl+M"),
    Shortcut("open_folder", "Open folder", "<Control-o>", "Ctrl+O"),
    Shortcut("reveal_file", "Reveal file", "<Control-Shift-O>", "Ctrl+Shift+O"),
    Shortcut("authenticate", "Authenticate / Import cookies", "<Control-Shift-A>", "Ctrl+Shift+A"),
    Shortcut("quit", "Quit (exit policy)", "<Control-q>", "Ctrl+Q"),
    Shortcut("tab_queue", "Switch to Queue tab", "<Control-Key-1>", "Ctrl+1"),
    Shortcut("tab_history", "Switch to History tab", "<Control-Key-2>", "Ctrl+2"),
    Shortcut("tab_thumbnails", "Switch to Thumbnails tab", "<Control-Key-3>", "Ctrl+3"),
    Shortcut("open_settings", "Open Settings", "<Control-comma>", "Ctrl+,"),
    Shortcut("shortcuts_help", "Open Keyboard shortcuts help", "<F1>", "F1"),
)

REQUIRED_ACTION_IDS = tuple(s.action_id for s in DEFAULT_SHORTCUTS)


def focus_is_text_entry(widget: Any) -> bool:
    if widget is None:
        return False
    name = widget.__class__.__name__.lower()
    return "entry" in name or name in {"text", "tktext", "ctktextbox"}


def should_ignore_event(event: Any) -> bool:
    """Ignore unmodified typing while focus is in a URL/text entry."""
    widget = getattr(event, "widget", None)
    if not focus_is_text_entry(widget):
        return False
    key = str(getattr(event, "keysym", "") or "").lower()
    if key.startswith("f") and key[1:].isdigit():
        return False
    state = int(getattr(event, "state", 0) or 0)
    has_mod = bool(state & _CTRL) or bool(state & _ALT) or bool(state & _MOD1)
    return not has_mod


class ShortcutRegistry:
    def __init__(self, shortcuts: tuple[Shortcut, ...] | list[Shortcut] | None = None) -> None:
        self._items: list[Shortcut] = list(shortcuts or DEFAULT_SHORTCUTS)
        self._handlers: dict[str, Callable[[], None]] = {}
        self._bound: list[tuple[Any, str, str]] = []

    def items(self) -> list[Shortcut]:
        return list(self._items)

    def action_ids(self) -> list[str]:
        return [s.action_id for s in self._items]

    def label_for(self, action_id: str) -> str:
        for spec in self._items:
            if spec.action_id == action_id:
                return spec.label
        raise KeyError(action_id)

    def help_lines(self) -> list[str]:
        return [f"{s.label}  —  {s.display}" for s in self._items]

    def bind_handler(self, action_id: str, handler: Callable[[], None]) -> None:
        self._handlers[action_id] = handler

    def invoke(self, action_id: str) -> None:
        fn = self._handlers.get(action_id)
        if fn is None:
            raise KeyError(f"no handler bound for {action_id}")
        fn()

    def install(self, widget: Any) -> None:
        """Bind sequences on *widget* (typically the app)."""
        for spec in self._items:
            aid = spec.action_id

            def _on(event: Any, action=aid) -> str | None:
                if should_ignore_event(event):
                    return None
                self.invoke(action)
                return "break"

            widget.bind(spec.sequence, _on)
            self._bound.append((widget, spec.sequence, aid))
