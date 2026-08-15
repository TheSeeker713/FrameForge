"""Copy text to the Flet clipboard (async Clipboard.set — not page.set_clipboard)."""

from __future__ import annotations

import inspect
from typing import Any


async def await_set_clipboard(page: Any, text: str) -> str:
    """Write *text* using Flet 0.86 Clipboard service, then sync fallbacks."""
    if page is None:
        return "none"
    written = False
    try:
        import flet as ft

        clip = None
        services = getattr(page, "services", None)
        if services is None:
            page.services = []
            services = page.services
        for item in list(services):
            setter = getattr(item, "set", None)
            if callable(setter) and type(item).__name__ == "Clipboard":
                clip = item
                break
        if clip is None and hasattr(ft, "Clipboard"):
            clip = ft.Clipboard()
            services.append(clip)
        if clip is not None:
            result = clip.set(text)
            if inspect.isawaitable(result):
                await result
            written = True
    except Exception:  # noqa: BLE001
        pass
    setter = getattr(page, "set_clipboard", None)
    if callable(setter):
        try:
            result = setter(text)
            if inspect.isawaitable(result):
                await result
            written = True
        except Exception:  # noqa: BLE001
            pass
    try:
        page.clipboard = text
        written = True
    except Exception:  # noqa: BLE001
        pass
    return "set" if written else "none"


def request_set_clipboard(page: Any, text: str) -> str:
    """Schedule or synchronously set clipboard. Never leaves an un-awaited coroutine."""
    if page is None:
        return "none"
    setter = getattr(page, "set_clipboard", None)
    if callable(setter):
        try:
            result = setter(text)
            if inspect.isawaitable(result):
                close = getattr(result, "close", None)
                if callable(close):
                    close()
            else:
                try:
                    page.clipboard = text
                except Exception:  # noqa: BLE001
                    pass
                return "sync"
        except Exception:  # noqa: BLE001
            pass
    try:
        page.clipboard = text
    except Exception:  # noqa: BLE001
        pass
    runner = getattr(page, "run_task", None)
    if callable(runner):
        try:
            future = runner(await_set_clipboard, page, text)
            if inspect.isawaitable(future):
                close = getattr(future, "close", None)
                if callable(close):
                    close()
                return "closed"
            return "scheduled"
        except Exception:  # noqa: BLE001
            pass
    return "sync" if getattr(page, "clipboard", None) == text else "none"
