"""Marshal callbacks onto the Tk main thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def schedule_on_ui(widget: Any, fn: Callable[[], None]) -> None:
    """Run *fn* on the Tk thread via ``after(0, ...)``.

    Worker, tray, and resource-monitor threads must not touch CTk widgets
    directly. If *widget* has no ``after`` (tests / already destroyed), *fn*
    runs inline.
    """
    after = getattr(widget, "after", None) if widget is not None else None
    if callable(after):
        try:
            after(0, fn)
            return
        except Exception:  # noqa: BLE001
            pass
    fn()
