"""Window close / process teardown for the Flet desktop shell.

## Why

v0.5.0 never hooked `FrameForgeUi.shutdown()` to the native window. Closing the
window left the Flet asyncio server (ProactorEventLoop on Windows) alive. The
next `python -m frameforge --gui` then hit `ConnectionResetError` / pipe noise.

v0.5.2 still **froze in the field** (RustDesk): the X button left a stuck GUI
because `prevent_close=True` and teardown could hang inside `page.update()` /
worker stop before `os._exit`.

## Path (v0.5.3)

1. `attach_page` sets `page.window.prevent_close = True` and
   `window.on_event` → `handle_window_close`.
2. First idle close: release `prevent_close`, arm a **3s watchdog**, `shutdown`
   (worker stop timeout 2s), then `os._exit(0)` on a real `ft.Page`.
3. First busy close: Quit-busy modal (Cancel / Pause / Wait). If the modal
   cannot open, teardown anyway.
4. **Second close click always force-kills** (escape hatch when the modal or
   GUI is stuck).
5. Watchdog: if `exit_process_on_quit` and teardown hangs > 3s → `os._exit(1)`.
   Tests keep `exit_process_on_quit=False` so pytest is never killed.
6. `run_gui` refuses a second `ft.app` in the same process (`_GUI_RUNNING`).
   `finally` also arms the watchdog and `_exit`s if the window loop returned
   without a clean shutdown.

Tests call `handle_window_close` with `exit_process_on_quit=False` (default
until `attach_page` sees a real `ft.Page`) and assert `_shutdown_complete`
without exiting the pytest process.
