"""Await Flet Window.destroy/close so the HWND actually dies."""

from __future__ import annotations

import inspect
from typing import Any


def consume_awaitable(result: Any) -> str:
    """Await-or-close a coroutine so it never warns 'was never awaited'.

    Returns ``awaited`` / ``closed`` / ``sync``.
    """
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


async def await_window_destroy(win: Any) -> str:
    """Await destroy, then close. Never leaves an un-awaited coroutine."""
    if win is None:
        return "none"
    try:
        win.prevent_close = False
    except Exception:  # noqa: BLE001
        pass
    for name in ("destroy", "close"):
        fn = getattr(win, name, None)
        if not callable(fn):
            continue
        try:
            result = fn()
        except Exception:  # noqa: BLE001
            continue
        if inspect.isawaitable(result):
            try:
                await result
                return name
            except Exception:  # noqa: BLE001
                consume_awaitable(result)
                continue
        return name
    return "none"


def request_window_destroy(page: Any, *, wait: float = 0.0) -> str:
    """Schedule or safely invoke window destroy. Never emits an un-awaited warning.

    * ``awaited`` — ``run_task`` future finished within *wait*.
    * ``scheduled`` — ``page.run_task`` accepted the async teardown.
    * ``sync`` — destroy/close ran as a normal function (tests / fakes).
    * ``closed`` — coroutine was created but could not be scheduled; closed.
    * ``none`` — no window.
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
            if inspect.isawaitable(future):
                consume_awaitable(future)
                return "closed"
            if wait > 0 and hasattr(future, "result"):
                try:
                    future.result(timeout=wait)
                    return "awaited"
                except Exception:  # noqa: BLE001
                    return "scheduled"
            return "scheduled"
        except TypeError:
            try:
                runner(await_window_destroy)
                return "scheduled"
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

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
