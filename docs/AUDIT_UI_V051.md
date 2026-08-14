# GUI interaction audit — FrameForge v0.5.1

HEAD baseline: `532252f` (v0.5.0). Flet 0.86.5. Presentation: `src/frameforge/ui_flet/`. Dialogs are `ft.AlertDialog` shown with `page.show_dialog` / closed with `page.pop_dialog` (not `page.dialog =`).

## Root causes (user bugs)

| Bug | Cause |
|-----|--------|
| Authenticate cannot close; app freezes | `on_close` only flipped `auth_open`; never `pop_dialog`. `on_firefox` / `on_txt` were `lambda: None`. `modal=True` blocked click-outside. No `on_dismiss`. |
| Import TXT/MD does nothing | `import_file` set `_pending_import = True` only. No FilePicker, no `preview_import`. |
| More does nothing | `PopupMenuButton(content=OutlinedButton("More"))` nested button swallowed clicks. `on_select` read `e.control.data` on the **menu button**, not the item. |
| Queue has almost no actions | Floating bar only when `selected_ids` non-empty. No always-on chrome for Clear finished / Retry failed. |
| Ghost window while dragging | Native `page.window.bgcolor` left `None` (transparent HWND) + `shadow=True`. DWM shows a stale copy while the Flutter view moves. |
| Stuck Flet/Proactor after close | `shutdown()` never hooked to `window.on_event` CLOSE / `page.on_disconnect`. Process kept the asyncio server. |

## Modal inventory

| Modal | Open path | Close path (v0.5.0) | Buttons | Transport |
|-------|-----------|---------------------|---------|-----------|
| **Authenticate** | Header shield → `open_authenticate` | Flag only (`auth_open=False`). X / Esc / barrier **dead** | Firefox, cookies.txt, Cancel, Done — Cancel/Done did not pop | `show_dialog` |
| **Settings** | Header gear → `open_settings` | Cancel/Save → `pop_dialog` | Cancel, Save (Save persists settings) | `show_dialog`; second open re-shows same instance |
| **Import confirm** | *unwired* (`open_bulk_confirm` tests only) | Flag `bulk_open` | Add to queue, Cancel | constructed only |
| **Fail-pause** | `UiBridge` → `_on_fail_pause` | Action lambdas `pop_dialog` | Import from browser, Authenticate, Retry, Skip, Stop | `show_dialog`; `modal=True`; no X |
| **Playlist** | `open_playlist_modal` (tests) | Flag only | Enqueue, Cancel; Select all/none unwired | constructed only |
| **Set format** | overflow / More set flags; **did not `show_dialog`** | Flag only | Apply, Cancel | constructed only |
| **Quit while busy** | *not hooked to window close* | Cancel no-op; choices set `quit_choice` only | Three quit tiles + Cancel | constructed only |
| **More menu** | Floating bar `PopupMenuButton` | n/a (not a dialog) | Items never fired | nested button + bad `on_select` |
| **Card overflow** | Per-card `PopupMenuButton` | n/a | Same `e.control.data` bug | menu |

## Contract (v0.5.1)

Single `DialogHost`: at most one dialog. `close()` always `pop_dialog`, `open=False`, `page.update()`, clears kind flags. `on_dismiss`, red X, Cancel, Escape, and click-outside (`modal=False`) all call `close()`. Second open of the same kind focuses the existing instance (no stack). Successful Authenticate actions close; errors stay inside the modal.

## Shutdown path

See [UI_SHUTDOWN.md](UI_SHUTDOWN.md). Window CLOSE → `handle_window_close` → quit policy → `shutdown()` (worker stop + repo close) → `window.destroy()` → `os._exit(0)` so the Flet desktop server cannot linger.
