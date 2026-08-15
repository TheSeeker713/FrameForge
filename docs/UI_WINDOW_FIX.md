# Window drag / visibility — v0.5.4

## Field report

v0.5.1–0.5.3 kept the **native Windows caption** and tried to stop outline-only
drag by setting opaque `bgcolor` / `shadow=False` / DWM Mica off. The user
retested **on local Windows 11 Pro** (not remote desktop). Drag was still
outline-only. Re-applying bgcolor is **not** a fix.

## v0.5.4 escalation (new mechanism)

FrameForge **no longer uses the native DWM title bar for dragging**.

1. `window.title_bar_hidden = True` (native caption and caption buttons off).
2. A Flutter `WindowDragArea` custom title bar (`build_custom_title_bar`) is
   the drag surface. Content is painted by Flutter during the gesture instead
   of DWM’s live thumbnail of a possibly-transparent HWND.
3. Custom **Minimize / Maximize / Close**. Close calls the same quit dialog as
   Alt+F4 / Ctrl+Q (`handle_window_close`), including Force quit.
4. Opaque `#F8FAFC` fill, `frameless=False` (resize border kept), DWM Mica /
   glass / iconic-thumbnail flags still forced off.

## Tradeoffs

- Windows 11 snap layouts on the native maximize button are gone; double-click
  the custom bar still maximizes (`WindowDragArea(maximizable=True)`).
- The caption is a 36px Flutter strip, not the OS chrome.
- If Flet 0.86.5 still blanks the Flutter view during `WindowDragArea` drag on
  AMD iGPU, that is a compositor limit FrameForge cannot patch. Workarounds:
  maximize then restore, or Win+Arrow. Do not treat bgcolor-only patches as a
  fix.

## Honesty

This is a **different window strategy**, not another bgcolor pass. Eyes-on
confirm on the user’s Win11 + Radeon 680M is still required before calling
drag fully Fixed in the field.
