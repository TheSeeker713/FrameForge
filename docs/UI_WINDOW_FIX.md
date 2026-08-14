# Window drag ghost — v0.5.1

## Symptom

Dragging the Flet desktop window on Windows showed a stale/ghost copy. The real window jumped to the drop position only after mouse release.

## Root cause

Flet 0.86 maps to a Flutter Windows HWND. When `page.window.bgcolor` is left `None`, that HWND is composited as **transparent**. Desktop Window Manager then shows the previous framebuffer as a ghost while the (opaque) Flutter view lags behind the native move. `window.shadow = True` adds a second shadow window that is especially laggy on AMD iGPU (Radeon 680M).

This was not a second `ft.app` / extra view in v0.5.0, but `run_gui` now also refuses a second instance in the same process.

## Fix (`apply_page_chrome`)

- `page.window.bgcolor = "#F8FAFC"` (same as `page.bgcolor`) — opaque native window
- `page.window.opacity = 1.0`
- `page.window.shadow = False`
- Keep the **native** title bar (`title_bar_hidden=False`, `frameless=False`) so Windows owns the drag
- One `ft.app` per process (`_GUI_RUNNING`)

No custom title-bar drag (`start_dragging`) is used.
