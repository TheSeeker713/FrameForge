# Window drag / visibility — v0.5.3

## Field report (v0.5.2 claim **failed**)

v0.5.1/v0.5.2 set `window.bgcolor = #F8FAFC` and `window.shadow = False` **once** at attach. On a real Windows 11 session (RustDesk remote, AMD iGPU) the window still went **invisible except the outline** while dragging. Tests that only asserted those flags were not enough.

## v0.5.3 attempt

1. Opaque `#F8FAFC` on **both** `page.bgcolor` and `window.bgcolor` (never `None`, never alpha).
2. Re-apply those flags on **every window event** and UI tick — not only first attach. Size is set only once so drag is not fought.
3. `window.shadow = False`, native title bar, `frameless = False`, `transparent = False` when the attribute exists.
4. Windows 11: `DwmSetWindowAttribute` to disable Mica/acrylic / DWM glass on the foreground HWND.
5. `chrome_snapshot(page)` records the live flags for debugging.

No custom title-bar `start_dragging`. Widget hover shadows stay on controls only.

## Workaround if drag is still outline-only

Maximize then restore, or move the window via Win+Arrow. This is a Flet 0.86.5 / Flutter Windows compositor limitation on some GPUs; FrameForge cannot fully replace DWM. Confirm on hardware with [ACCEPTANCE_V053.md](ACCEPTANCE_V053.md) item 9.
