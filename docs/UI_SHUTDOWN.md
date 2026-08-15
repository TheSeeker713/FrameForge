"""Window close / process teardown for the Flet desktop shell.

## Why

v0.5.0 never hooked `FrameForgeUi.shutdown()` to the native window. Closing the
window left the Flet asyncio server (ProactorEventLoop on Windows) alive. The
next `python -m frameforge --gui` then hit `ConnectionResetError` / pipe noise.

v0.5.2–0.5.4 still left a stuck HWND: `prevent_close=True`, teardown that hung,
and **`Window.destroy()` / `Window.close()` are async in Flet 0.86**. Calling
them as sync functions produced `RuntimeWarning: coroutine Window.destroy was
never awaited`. Python then `_exit`ed while **flet.exe kept the window**.

## Path (v0.5.5)

X, Alt+F4, custom Close, and Ctrl+Q always open the quit dialog.

1. Idle: **Quit** + Stay + **Force quit now**.
2. Busy: Cancel and quit / Pause and quit / Wait / Stay / Force quit now.
3. `request_window_destroy` **awaits** `window.destroy` via `page.run_task`.
   If a coroutine cannot be scheduled, it is closed (never left un-awaited).
4. Force quit: stop worker → await destroy → kill descendant PIDs (`flet.exe`)
   **before** `_exit` (never `taskkill` self first, which orphans the GUI).
5. Watchdog `_exit` if teardown hangs. Tests keep `exit_process_on_quit=False`.
6. Second close click while the dialog is up still force-kills.

Tests assert destroy is awaited without a RuntimeWarning and that Force quit
marks the fake window destroyed.
