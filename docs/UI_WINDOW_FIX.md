# Window drag — v0.5.7 PASS via native title bar

## Field history

v0.5.1–0.5.3 kept the native caption and tried opaque `bgcolor` / `shadow=False`.
Drag was still outline-only on local Win11 Pro.

v0.5.4 hid the native caption (`title_bar_hidden=True`) and used a Flutter
`WindowDragArea`. That was also outline-only, and a later DWM experiment
applied attributes to **File Explorer** via `GetForegroundWindow` (see
[SHELL_SAFETY.md](SHELL_SAFETY.md)). Custom drag is **not** the product path.

## v0.5.7 (PASS)

FrameForge uses the **native Windows title bar** again for dragging.

1. `window.title_bar_hidden = False` (OS caption + min/max/close).
2. `window.title_bar_buttons_hidden = False`.
3. `USE_CUSTOM_TITLE_BAR = False` — `build_custom_title_bar` / `WindowDragArea`
   is **not** in the default GUI tree.
4. Opaque `#F8FAFC` page/window bgcolor only. **Zero DWM**
   (`DwmSetWindowAttribute` is not called).
5. Native **X** still hits `prevent_close=True` → quit dialog / Force quit
   (`handle_window_close`, Ctrl+Q unchanged).

Drag the **native** title strip: Windows paints the live window. That is the
measurable PASS. Do not re-enable `WindowDragArea` as default chrome.

## Shell safety

Never `GetForegroundWindow`, never DWM on a foreign HWND, never theme keys,
never restart `explorer.exe`. Reveal-file remains `explorer /select,<path>`.
