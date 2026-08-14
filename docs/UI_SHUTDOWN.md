"""Window close / process teardown for the Flet desktop shell.

## Why

v0.5.0 never hooked `FrameForgeUi.shutdown()` to the native window. Closing the
window left the Flet asyncio server (ProactorEventLoop on Windows) alive. The
next `python -m frameforge --gui` then hit `ConnectionResetError` / pipe noise.

## Path

1. `attach_page` sets `page.window.prevent_close = True` and
   `window.on_event` → `handle_window_close`.
2. `page.on_disconnect` and `page.on_close` call the same teardown if needed.
3. `handle_window_close` uses `classify_exit` (`frameforge.gui.exit_policy`):
   - active download/upscale → Quit-busy modal (Cancel / Pause / Wait)
   - idle → `_finish_exit`
4. `_finish_exit` closes any dialog, `worker.stop()`, `repo.close()`, then
   `window.prevent_close = False` + `window.destroy()` / `close()`.
5. On a real `ft.Page` only (`exit_process_on_quit`), `os._exit(0)` kills the
   Flet desktop process so a second launch is a clean process.

Tests call `handle_window_close` with `exit_process_on_quit=False` (default
until `attach_page` sees a real `ft.Page`) and assert `_shutdown_complete`
without exiting the pytest process.

`run_gui` refuses a second `ft.app` in the same process (`_GUI_RUNNING`).
"""
