# Windows shell safety

FrameForge must never change File Explorer, DWM session themes, or other apps’ windows.

## Incident

`disable_dwm_glass()` in `src/frameforge/ui_flet/window_chrome.py` called `GetForegroundWindow()` and then `DwmSetWindowAttribute` on that HWND. `apply_page_chrome` re-ran on window-event ticks. If File Explorer (or any other app) was focused, those DWM attributes were applied to **Explorer**, not FrameForge. The shell could flip to a classic / Win95-like look until Explorer was closed and reopened.

Foreground window is **not** “our window.”

## Fix (v0.5.6)

- Removed all `GetForegroundWindow` / `DwmSetWindowAttribute` usage from the chrome path.
- FrameForge chrome is **Flet-only** (`page` / `page.window` bgcolor, opacity) plus the **native OS title bar** (`title_bar_hidden = False`). No `WindowDragArea` by default. Zero DWM.
- If a native HWND is needed later, it must come from the FrameForge/Flet window object. Unknown handle → **no-op**.
- Reveal-in-folder still uses `explorer /select,<path>` only. It does not kill `explorer.exe` or write theme keys.

## Permanent ban

See `.cursor/rules/windows-shell-safety.mdc`. Do not reintroduce:

- HKCU/HKLM ThemeManager / Personalize / Explorer Advanced “fixes”
- `SetThemeAppProperties`, foreign `SetWindowTheme`, session `SystemParametersInfo` UI toggles
- DWM chrome on any HWND that is not proven FrameForge
- `GetForegroundWindow()` as the app HWND
- Restarting `explorer.exe` as a repair
