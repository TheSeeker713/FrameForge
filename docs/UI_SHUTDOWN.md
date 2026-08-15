"""Window close / process teardown for the Flet desktop shell.

## Why

v0.5.0 never hooked `FrameForgeUi.shutdown()` to the native window. Closing the
window left the Flet asyncio server (ProactorEventLoop on Windows) alive. The
next `python -m frameforge --gui` then hit `ConnectionResetError` / pipe noise.

v0.5.2–0.5.3 still left a stuck HWND in the field: `prevent_close=True` plus
teardown that hung inside `page.update()` / worker stop before `os._exit`. Idle
close skipped the dialog and called `_finish_exit` immediately, which could
look like a no-op when Flet never delivered a second close.

## Path (v0.5.4)

X, Alt+F4 (`close` / `close_prevented` window events), `page.on_close`, and
Ctrl+Q **always** enter the quit dialog. Idle is never a silent `_finish_exit`.

1. `attach_page` sets `page.window.prevent_close = True` and
   `window.on_event` → `handle_window_close`.
2. **First close (idle or busy):** open the quit dialog.
   - Idle: “Quit FrameForge?” with Quit / Stay / **Force quit now**.
   - Busy (download/upscale/convert, or wait-then-quit still running):
     Cancel and quit / Pause and quit / Wait until finished / Stay /
     **Force quit now**.
3. Stay and Wait reset the close-click counter so the next X opens the dialog
   again instead of force-killing.
4. **Second close click while the dialog is up always force-kills** (escape
   hatch when the modal or GUI is stuck).
5. **Force quit now** releases `prevent_close`, arms a 0.5s watchdog, stops
   the worker, closes the repo, then `force_kill_current_app()` (kill this
   PID + children including `flet.exe`, then `os._exit(1)`).
6. Watchdog: if `exit_process_on_quit` and teardown hangs → `os._exit(1)`.
   Tests keep `exit_process_on_quit=False` so pytest is never killed.
7. `run_gui` refuses a second `ft.app` in the same process (`_GUI_RUNNING`).
   `finally` also arms the watchdog and `_exit`s if the window loop returned
   without a clean shutdown.

Tests call `handle_window_close` with `exit_process_on_quit=False` (default
until `attach_page` sees a real `ft.Page`) and assert `_shutdown_complete`
without exiting the pytest process.
