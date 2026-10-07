# Tray and quit policy

- The caption **minimize** button hides FrameForge to the system tray. Downloads keep running. There is no Settings toggle for this.
- Tray menu: **Show FrameForge**, **Pause current** / **Resume current**, **Download all pending**, **Import URL list**, **Import completed downloads**, **Quit**.
- Window **X**, **Ctrl+Q**, and tray **Quit** still use the quit policy. They do not hide.

Tray implementation: `pystray` + Pillow, `icon.run_detached()`. Flet callbacks are scheduled with `page.run_task`.

## Three quit options (active download or upscale)

If nothing is `downloading`/`upscaling`, FrameForge exits normally.

If work is active, a dialog asks for exactly one of:

1. **Cancel download and quit** — hard-cancel the active job (`cancelled`) and exit.
2. **Pause download and quit** — pause (keep partials), exit. On next launch the job stays `paused` until you Resume (no auto-resume).
3. **Wait for download to complete, then quit** — disarm further claims (no new pending jobs start), let the current stage finish, then exit. Cancel during wait clears the wait-to-quit flag and the app stays open.

These paths share `frameforge.gui.exit_policy` (window X, File → Quit, Ctrl+Q, tray Quit).
