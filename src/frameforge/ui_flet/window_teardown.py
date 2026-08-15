"""Schedule Flet Window.destroy without deadlocking the UI thread."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


def consume_awaitable(result: Any) -> str:
    """Close a leftover coroutine so it never warns 'was never awaited'."""
    if not inspect.isawaitable(result):
        return "sync"
    close = getattr(result, "close", None)
    if callable(close):
        try:
            close()
            return "closed"
        except Exception:  # noqa: BLE001
            pass
    return "closed"


def _on_page_loop_thread(page: Any) -> bool:
    """True when waiting on run_task would deadlock the Flet event loop."""
    try:
        loop = page.session.connection.loop
    except Exception:  # noqa: BLE001
        return False
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return running is loop


async def await_window_destroy(win: Any) -> str:
    """Await destroy only (not close — close re-fires prevent_close)."""
    if win is None:
        return "none"
    try:
        win.prevent_close = False
    except Exception:  # noqa: BLE001
        pass
    fn = getattr(win, "destroy", None)
    if not callable(fn):
        fn = getattr(win, "close", None)
    if not callable(fn):
        return "none"
    try:
        result = fn()
    except Exception:  # noqa: BLE001
        return "none"
    if inspect.isawaitable(result):
        try:
            await result
            return "destroy"
        except Exception:  # noqa: BLE001
            consume_awaitable(result)
            return "none"
    return "destroy"


def request_window_destroy(page: Any, *, wait: float = 0.0) -> str:
    """Schedule window destroy. Never block the Flet loop thread.

    Live quit always passes ``wait=0``. Waiting on ``Future.result`` from the
    UI thread deadlocks ``run_coroutine_threadsafe`` (Flet 0.86 ``run_task``).
    """
    if page is None:
        return "none"
    win = getattr(page, "window", None)
    if win is None:
        return "none"
    try:
        win.prevent_close = False
    except Exception:  # noqa: BLE001
        pass

    runner = getattr(page, "run_task", None)
    if callable(runner):
        try:
            future = runner(await_window_destroy, win)
        except TypeError:
            try:
                runner(await_window_destroy)
                return "scheduled"
            except Exception:  # noqa: BLE001
                future = None
        except Exception:  # noqa: BLE001
            future = None
        else:
            if inspect.isawaitable(future) and not hasattr(future, "result"):
                consume_awaitable(future)
                return "closed"
            if wait > 0 and hasattr(future, "result") and not _on_page_loop_thread(page):
                try:
                    future.result(timeout=wait)
                    return "awaited"
                except Exception:  # noqa: BLE001
                    return "scheduled"
            return "scheduled"

    for name in ("destroy", "close"):
        fn = getattr(win, name, None)
        if not callable(fn):
            continue
        try:
            result = fn()
        except Exception:  # noqa: BLE001
            continue
        if inspect.isawaitable(result):
            return consume_awaitable(result)
        return "sync"
    return "none"
