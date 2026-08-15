# Changelog

## 0.5.9

- Recover `download_path` after yt-dlp exit 0 via printed path, `*[id].*` glob, recent media, and info.json (`docs/OUTPUT_PATH.md`)
- Missing file after success is `output_missing` (not unknown/auth); fail-pause leads with Retry / Open folder, not Firefox
- Retry / Resume download returns cancelled and failed rows to pending without auto-start
- Progress ticks every 0.5s on the UI loop while a stage is active (including unfocused); aria2 SIZE without `%` still updates the bar
- Click a completed thumbnail to open the file in the default player
- BLOCKED 4K+ means upscale policy; idle line explains Stop / fail-pause when pending remain

## 0.5.8

- Quit: native X → “Quit FrameForge?” (Quit / Cancel only); UI and process tree exit on a hard deadline (`docs/UI_SHUTDOWN.md`)
- Aria2 stays default when installed; googlevideo HTTP 403 / aria2 exit 22 auto-retries once with the native yt-dlp downloader
- Those CDN blocks classify as `aria2_forbidden`, not `ffmpeg` (argv `--ffmpeg-location` is not an FFmpeg failure)

## 0.5.7

- Native Windows title bar for window drag (`title_bar_hidden=False`); custom `WindowDragArea` is not default chrome
- YouTube throughput: `-N 8`, aria2c `-x 16 -s 16`, `--throttled-rate 100K`, `--http-chunk-size 10M`; no silent `--limit-rate`
- Authenticate/Settings show the cookies folder and domain files, with Open cookies folder

## 0.5.6

- Shell safety: never `GetForegroundWindow` + DWM on foreign HWNDs (Explorer incident)
- YouTube Innertube `player_client` rotation for anonymous public downloads
- Worker passes `--js-runtimes deno[:path]`; EJS failures classified as `js_runtime` (not Re-authenticate)
- Auth UX leads with Firefox / cookies.txt; Chrome App-Bound Encryption is an honest limit
- ffmpeg discovery (PATH + WinGet Gyan); Flet Clipboard.set for Copy error; Download selected on pending
- Inter-job delay default 3s; thumbnails on completed cards; cancel during Starting; awaited window destroy

## 0.5.4

- Quit dialog always (idle and busy) with Stay and Force quit; watchdog still `_exit`s
- Pause and Stop while downloading; fail-pause halt latch so bulk does not claim the next job
- yt-dlp argv/cwd/cookies/aria2c/ffmpeg logged per job; sticky cookies and missing aria2c fixed
- Copy full error report on fail-pause, Authenticate, and failed job cards
- Custom Flutter `WindowDragArea` title bar (native DWM caption no longer used for drag)

## 0.5.3

- Clear finished only hides completed/failed/cancelled; Undo restores visibility
- Hard shutdown: second close force-kills; 3s watchdog; prevent_close released before teardown
- Live progress bar + header activity; failed cards obvious without selection
- Chrome and Edge cookie import; Authenticate stays open with in-dialog status
- Window chrome reapplied on move/tick; v0.5.2 drag-ghost claim failed the field test — confirm item 9 on hardware

## 0.5.2

- Hover elevation on cards and buttons (widget shadows only; window drag ghost stays gone)
- Bot-check playbook: classify stderr, validate cookies before resume, short gentle-rate cooldown
- PyInstaller one-folder Flet build revalidated (`dist\FrameForge\FrameForge.exe`)

## 0.5.1

- Emergency Flet interaction fix: dialogs close (X / Esc / barrier / Cancel)
- Import TXT/MD, More menu, and queue chrome (Clear finished / Retry failed) wired
- Window drag ghost (opaque HWND, no DWM shadow); process exits so the next `--gui` is clean
- Display version 0.5.1

## 0.5.0

- Full GUI rewrite on Flet (light SaaS chrome; CustomTkinter is not the default window)
- Floating selection bar; contextual Upscale / Convert
- Fail-pause on retry and hard unknown; stderr tail on yt-dlp exits
- Settings single-instance; display version 0.5.0

## 0.4.0

- Pause / resume downloads (hard-stop, keep partials, yt-dlp continue)
- Quit while busy: cancel, pause, or wait-for-current (exactly three options)
- Optional close-to-system-tray (default off); tray Show / Pause-Resume / Quit
- Import cookies from browser (Firefox first; Chromium fallback; manual Netscape still available)

## 0.3.0

- Original 11 items **100% PASS** (live subprocess speed/ETA; failure-driven auth hints)
- Structured error categories + richer error panel
- History tab (SQLite terminal jobs; soft-hide)
- Thumbnails cache + Queue/History previews + Thumbnails tab
- Worker loop survives handler exceptions; ORT dual-thread test race fixed

## 0.1.0

- Phase 0–5 initial release scaffold and application
- Sequential SQLite WAL queue
- yt-dlp + aria2c downloads
- TXT/MD bulk import
- ONNX upscale pipeline with stop/resume and audio preservation
- CustomTkinter dark GUI
- PyInstaller portable build
