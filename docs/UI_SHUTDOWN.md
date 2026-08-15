# Window close / process teardown

## Why field Quit has failed (v0.5.1–0.5.7) — root cause

Pytest `test_ui_flet_shutdown.py` stayed green because tests use `FakePage`,
`exit_process_on_quit=False`, and never start the Flet desktop **view** process.
The live path is different.

Flet 0.86 `ft.app()` / `ft.run()` starts a **separate** Flutter host
(`open_flet_view_async` → `flet.exe` / Flet View) and talks to it over a socket.
The HWND the user sees belongs to that child, not to Python.

### Bug 1 — Watchdog `_exit`s Python without killing the view (primary)

`force_quit` arms a 0.5s timer that calls **`os._exit(1)` only**. It does **not**
call `kill_gui_children()` / `close_flet_view`.

Meanwhile the same function still does:

1. `worker.stop(timeout=0.5)` (join can consume the whole 0.5s)
2. `request_window_destroy(..., wait=0.4)` which calls
   `Future.result(timeout=0.4)` on the **Flet event-loop thread**

`page.run_task` is `asyncio.run_coroutine_threadsafe(..., connection.loop)`.
Waiting on that Future **on the loop thread** deadlocks: destroy never runs
until the wait times out. Combined with worker join, the 0.5s watchdog often
fires **first**, `_exit`s Python, and **skips** child kill. The Flet View keeps
the window. Terminal may return; the GUI does not. Next `--gui` looks like a
stuck previous instance.

Idle **Quit** uses `_finish_exit` → `shutdown()` (`worker.stop(timeout=2)`) →
`request_window_destroy(wait=0.8)` with a **3s** watchdog that is also bare
`_exit(1)`. Same orphan-view failure if teardown blocks.

### Bug 2 — `Window.destroy()` is async; waiting on the UI thread freezes clicks

Flet 0.86 `Window.destroy` / `Window.close` are **coroutines**. Calling them as
sync work was already documented. The v0.5.5 “await via `run_task`” fix then
**blocks the loop** with `future.result()`. The dialog looks dead: Quit / Force
quit appear to do nothing until (or unless) the watchdog fires — and then see
bug 1.

`Window.close()` with `prevent_close=True` only re-sends `WindowEventType.CLOSE`
(there is no `CLOSE_PREVENTED` in 0.86). It does not destroy the HWND.

### Bug 3 — One native X can fire two handlers

`attach_page` sets both `page.on_close = handle_window_close` and
`window.on_event` → `handle_window_close` on `"close"`. `_close_clicks >= 2`
then **force-quits immediately**, often while the confirm dialog is still
opening. That races with bug 2 (deadlocked destroy) and leaves a dead modal.

### Bug 4 — Tick `page.update()` from a Timer thread during the dialog

`_schedule_tick` uses `threading.Timer` and calls `tick()` → `apply_page_chrome`
→ `page.update()` off the Flet loop. That is not thread-safe. Updates while the
quit dialog is open can freeze or swallow button clicks (Force quit “does
nothing”).

### What tests missed

- No assertion that **Flet View PID** is killed before `_exit`
- Watchdog tested as “timer armed”, not as “children dead”
- Fake `run_task` runs coroutines with `asyncio.run` (no deadlock)
- `exit_process_on_quit=False` never exercises `os._exit` or `kill_gui_children`

## Path (v0.5.8) — simple confirm, then hard deadline

Native X / Ctrl+Q → **“Quit FrameForge?”** (or “A download is in progress. Quit
anyway?”) with **Quit** and **Cancel** only. No Cancel/Pause/Wait/Force stack.

On **Quit**:

1. Stop ticks; `prevent_close = False`
2. Hard-kill in-flight yt-dlp / aria2c / ffmpeg trees
3. Schedule `window.destroy` **without waiting on the UI thread**
4. `kill_gui_children()` (Flet View HWND)
5. `os._exit(0)` within ~0.35s; watchdog at **3s** does the same
   **kill children then `_exit(0)`** so a hung join cannot orphan the GUI

**Cancel** closes the confirm and leaves the app usable.

Tests keep `exit_process_on_quit=False`. A subprocess test proves `hard_exit`
actually terminates a Python process.
