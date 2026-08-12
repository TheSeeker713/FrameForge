# Tray and quit policy

## Close to tray

Settings → **Close to system tray** (default **off**).

- **On:** window **X** hides the window (`withdraw`) and shows a system tray icon. The sequential worker keeps running in the background. Pending jobs still do **not** auto-start.
- **Off:** window **X** uses the quit policy below.

File → **Quit**, **Ctrl+Q**, and tray **Quit** always use the quit policy (they do not hide).

Tray implementation: `pystray` + Pillow, `icon.run_detached()` so CustomTkinter’s mainloop is not blocked. Tray callbacks marshal UI work with `widget.after(0, …)`.

### Tray menu

- **Show window** — `deiconify`
- **Pause current** / **Resume current** — same worker methods as the queue buttons
- **Quit** — quit policy

## Three quit options (active download or upscale)

If nothing is `downloading`/`upscaling`, FrameForge exits normally.

If work is active, a dialog asks for exactly one of:

1. **Cancel download and quit** — hard-cancel the active job (`cancelled`) and exit.
2. **Pause download and quit** — pause (keep partials), exit. On next launch the job stays `paused` until you Resume (no auto-resume).
3. **Wait for download to complete, then quit** — disarm further claims (no new pending jobs start), let the current stage finish, then exit. Cancel during wait clears the wait-to-quit flag and the app stays open.

These paths share `frameforge.gui.exit_policy` (window X, File → Quit, Ctrl+Q, tray Quit).
