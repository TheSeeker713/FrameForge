# Changelog

## 0.6.31

- Eporner’s “Authorization failed. Try to reload page” was the site API rejecting the wrong hash. The page has a user hash and a player hash, and yt-dlp was sending the user hash. FrameForge now sends player.hash, retries the embed page once if the API still refuses, then tries browser cookies once.

## 0.6.30

- An album is a link in the database. Placing a clip in an album, or removing it from the library, leaves the file where it is. Indexing a completed download does not move that file.

## 0.6.29

- `scripts/reset_queue.ps1` clears the queue and the download archive in the onboarded database. Video files, cookies, the home pointer, and library rows stay. It refuses while a download is running.

## 0.6.28

- A document import keeps every http(s) link, including ones that only exist as Word hyperlinks and ones whose path says search, tag, or category. A URL split across lines is one job. The confirm dialog shows listings seen, URLs found, duplicates skipped, and rows to add. Those rows are inserted in one database transaction off the window thread. The import does not start downloads.

## 0.6.27

- The window X opens “Quit FrameForge?” immediately. It does not query the database, and a second X does not quit. Quit runs only from the Quit button. If a download is in progress, the dialog says so from the worker’s in-memory flag. Minimize still hides to the tray.

## 0.6.26

- “Video is not available” from Eporner is the site API rejecting a page that was not fetched as a browser. Eporner is now fetched as Chrome, and that sentence retries once as a browser before the job fails. It does not ask for cookies and does not pause the queue.

## 0.6.25

- The queue pauses only for a real wall: login, age check, bot check, a missing JavaScript runtime, missing browser impersonation, a missing output file, or a full disk. An unclassified failure fails that job and continues. It does not ask for cookies. Copying the error report includes the per-job log.

## 0.6.24

- Aria2 is used for plain HTTP files only, at 8 connections. HLS and DASH stay on the built-in downloader, and so does any host that needs browser impersonation. A CDN 403 retries once at 4 connections, then once with the built-in downloader.

## 0.6.23

- “Video is not available” is an unavailable video. The queue does not pause, does not ask for cookies, and does not switch to the generic extractor after a named site extractor has already answered.

## 0.6.22

- A failed job card leads with the extractor sentence. A warning such as “only images are available” stays above “the downloaded file is empty,” and the full text is written to a log under the FrameForge temp folder. yt-dlp warnings are no longer discarded.

## 0.6.21

- The Library tab is a cover-flow shelf of the indexed clips. Click a side card to bring it forward, and click the front card to play it in FrameForge. Albums are links in the database: a clip is in one album at a time, and removing it from the library leaves the file where it is. Sort includes duration.

## 0.6.20

- An empty download is no longer treated as a login failure. When the fast downloader writes a 0-byte file, FrameForge deletes that file and retries once with the built-in downloader. The queue does not pause and does not ask for cookies.

## 0.6.19

- The Settings “Close to system tray” switch is gone. The window minimize button hides FrameForge to the tray and leaves the download running. The tray menu can show the window, pause or resume, start pending downloads, import a URL list, and import completed downloads.

## 0.6.18

- The Windows `Downloads\FrameForge` folder is created only when onboarding chooses that default. A custom folder keeps the database, cookies, models, thumbnails, and videos together under `<picked>\FrameForge`.

## 0.6.17

- Library rows show thumbnails and play inside FrameForge. Queue and History still open the Windows default player.
- The Flet window no longer starts Windows location. FrameForge does not read or send coordinates; the stock Flet client was constructing a WinRT Geolocator at launch. That plugin is replaced with a no-op.
- When cookies for the failing site are already validated this session, the queue retries and resumes on its own. The pause dialog remains for a later failure, or when cookies are not validated.

## 0.6.16

- First launch asks where new videos should go. Choose a folder, or skip and use the Windows user folder (`%USERPROFILE%\Downloads\FrameForge\downloads`). The queue, cookies, and models stay in the app home. A local disk used for downloads is a folder on this PC, not a network share.

## 0.6.15

- Bulk import reads `.txt`, `.md`, `.rtf`, `.doc`, and `.docx`. A heading in the document is the category (first two words). Each link’s host picks the folder: `downloads/<bucket>/<category>/`. YouTube, social, news, and adult hosts share that rule. Listing and search URLs are skipped. Import still only queues pending jobs.
- New Private packs use AES-256-GCM. Older ZipCrypto packs still open. Decrypted playback files under `Private/play` are removed on quit.
- The app root is no longer a path compiled into source. Order: `FRAMEFORGE_ROOT`, `%APPDATA%\FrameForge\root.txt`, then `%USERPROFILE%\Downloads\FrameForge`. On Windows, the cookies and database folders are limited to the current user.

## 0.6.14

- Library / Queue / History: working **Select all** (and Clear selection) so bulk Add to collection, Remove, Delete files, Upscale, Private, re-download, and clear actually apply to every visible clip.
- Downloads live under `downloads/<bucket>/<category>/` (adult → `downloads/porn/<category>/`); leftover root site folders migrate into that tree. Completed downloads index into Library in place. See [SITE_FOLDERS.md](docs/SITE_FOLDERS.md), [FOLDER_LAYOUT.md](docs/FOLDER_LAYOUT.md), [LIBRARY.md](docs/LIBRARY.md).
- Real-ESRGAN x4plus ONNX install script uses the Qualcomm release zip (old GitHub URL 404). Authenticate-site dialog layout no longer overlaps action buttons.

## 0.6.13

- P0: silent Firefox cookie recovery no longer hangs the sequential worker. Hard **60s** total timeout (process tree killed), file-only Netscape validate (no live `extract_info` probe), unknown failures no longer re-import just because a cookie file exists. Timeout/import fail → fail-pause once; Download all / Retry / Skip / Stop clear the halt latch. `auto_cookie_recovery` OFF is the pre-recovery download path (no Firefox wait). Recovery exceptions are logged and fail the job — they do not kill the worker thread. See [FAIL_PAUSE.md](docs/FAIL_PAUSE.md), [COOKIES.md](docs/COOKIES.md).

## 0.6.12

- Auto recovery now runs the **same two fail-pause buttons** before any modal: Import from Firefox (await 10–15s+, timeout 120s) → interruptible backoff → Retry this job. Stops after impersonate was a field regression (`unknown` + `tried: impersonate`). Unknown failures enter this path when stderr is auth-like, the domain already has cookies, the host is on Auto impersonate, or impersonate was already tried. All sites. See [FAIL_PAUSE.md](docs/FAIL_PAUSE.md), [COOKIES.md](docs/COOKIES.md).

## 0.6.11

- Auto Firefox cookie recovery before fail-pause for **every domain** (not PornHub-only): on auth/bot/rate/impersonation_missing and stderr-matched soft-unknown walls, import Firefox (Edge fallback, never Chrome ABE) once, then **interruptible worker-thread backoff** (`auto_retry_backoff_sec` default 5 + optional jitter default 2) and one retry. Status shows `Waiting Ns before retry…`. Human modal only if that path fails. Cancel/pause aborts the wait (no retry). See [FAIL_PAUSE.md](docs/FAIL_PAUSE.md), [COOKIES.md](docs/COOKIES.md), [MULTI_SITE.md](docs/MULTI_SITE.md).

## 0.6.10

- GUI/worker start without ONNX: missing models dir is no longer a `FileNotFoundError` on `python -m frameforge --gui`. Category `upscale_config` if upscale is forced anyway.
- Chunked upscale (default 128-frame PNG chunks, then encode and delete) so long clips are not a full-film PNG dump; duration is a soft warning, not a 15-minute hard fail. Original audio still muxed. ≥2160p still blocked.
- Models dir is created on startup; empty dir logs once and may write smoke Identity ONNX (not Real-ESRGAN). See [UPSCALE_DISK.md](docs/UPSCALE_DISK.md).

## 0.6.9

- Multi-site hardening: automatic recovery ladder (impersonate → silent Firefox/Edge cookies → generic extractors once), `drm_blocked` category, expanded Auto impersonate host list, fail-pause / error report show `tried: …` ([MULTI_SITE.md](docs/MULTI_SITE.md))
- `--check-env` reports `extractor_count`; Add URL probe badges `[generic]` when applicable
- Honest limit: thousands of sites via yt-dlp extractors + generic — not a guarantee against upstream breakage or DRM

## 0.6.8

- PornHub / MindGeek: `--impersonate chrome` when curl_cffi targets exist; pin `curl_cffi==0.13.0` (do not upgrade to 0.16.x with yt-dlp 2026.07.04)
- Job-70-style HTTP 410 / “no impersonate target” classifies as `impersonation_missing`, not `unknown`; 410 after impersonate+cookies is `not_available` (confirm in browser)
- `--check-env` reports yt-dlp, curl_cffi, Chrome availability, and impersonate clients
- Docs: [ADULT_SITES.md](docs/ADULT_SITES.md), [COOKIES.md](docs/COOKIES.md), [YTDLP_PARITY.md](docs/YTDLP_PARITY.md)

## 0.6.7

- Library Move: chunked cancellable cross-drive copy (no `copy2`), progress bytes, path dedupe, heal missing Uncategorized job paths from youtube/…, Reset dialog no longer vanishes under Settings dismiss ([LIBRARY.md](docs/LIBRARY.md), [AUDIT_FULL_v0.6.3_FIELD.md](docs/AUDIT_FULL_v0.6.3_FIELD.md))
- **Not claimed fixed** for the live 4.5 GB youtube tree until a field log from that tree shows `OK #2+`

## 0.6.6

- Worker cancel is typed (`DownloadCancelled` / user status) only — yt-dlp “Cancelled by the uploader” is `not_available` failed, not user-cancelled ([FAIL_PAUSE.md](docs/FAIL_PAUSE.md), [YTDLP_PARITY.md](docs/YTDLP_PARITY.md))

## 0.6.5

- SQLite: thread-local connections (`check_same_thread=True`), WAL kept; GUI and worker no longer share one Connection ([SQLITE_THREADING.md](docs/SQLITE_THREADING.md))
- Transient `OperationalError` on claim/progress requeues the job; exhausted DB failures use category `db_error` (not yt-dlp `unknown`); `_fail_stuck_active_stages` ignores a single transient lock

## 0.6.4

- Upscale PNG pipeline: estimate peak temp and refuse with category `disk_space` when free space is insufficient; default 15-minute duration cap (`upscale_limit`) until streaming lands ([UPSCALE_DISK.md](docs/UPSCALE_DISK.md))
- Delete `temp/<job>/frames` after a successful mux (and after terminal fail unless debug keep-frames); Repair sweeps orphan frame dirs older than 24h without touching `temp/dl`

## 0.6.3

- Library migrate writes `temp/library_move_<timestamp>.log` (src/dst/ok/fail). Stale missing `library_items` no longer block re-move. Real 3-file cross-drive Move: `moved=3` ([FIELD_MIGRATE_v0.6.3.md](docs/FIELD_MIGRATE_v0.6.3.md))
- Settings **Repair folders** shows working state and a completion summary (not silent)
- Repair relocates `.part` / `.aria2` / `.ytdl` to `temp/junk/` and `.info.json` to `metadata/` (no Recycle)
- yt-dlp temp outputs use `temp/dl/`; finished media stays in the per-site folder

## 0.6.2

- Audit named the 1-file migrate abort: progress callbacks sat outside the per-file try, and the runner discarded the in-progress report ([AUDIT_LIBRARY_MIGRATE_v0.6.2.md](docs/AUDIT_LIBRARY_MIGRATE_v0.6.2.md))
- Migrate continues after per-file **and** callback errors; cross-drive uses copy2 → size verify → unlink
- Startup/Settings **Repair folders** sweeps all site folders: thumbs → `thumbnails/`, leftover SQLite → `database/`, junk candidates listed not deleted (background thread)
- `scripts/reset_library_state.ps1` alias for clean onboarding retest

## 0.6.1

- Library grid shows one playable card per indexed file; click thumb/card plays in the default player
- Missing paths re-found under `library_root`; **Scan library folder** indexes disk orphans
- Migrate scans completed jobs **and** videos under the download tree; progress stays until a summary (not toast-only)
- Library pick creates `<picked>/FrameForge/Library/…`; init repairs thumbs/db/loose videos into subfolders ([FOLDER_LAYOUT.md](docs/FOLDER_LAYOUT.md))
- Settings → Advanced or `.\scripts\reset_library.ps1` resets onboarding without deleting media
- Duplicate merge by normalized title + size + duration (Recycle Bin for extras)
- Junk triage (`.part` / sidecars / zero-byte) — Recycle Bin only, or Keep / Move

## 0.6.0

- Library tab replaces Thumbnails: local folder + SQLite only (no cloud)
- First-open onboarding picks a library root and can move completed downloads into `Uncategorized/`
- Later opens prompt only for **new** completed files not yet indexed
- Seeded sources/types/subjects; custom collections; tag-to-folder sort (one primary path, extra tags)
- Upscale from Library when height < 2160; Queue playback unchanged
- Settings: change library root (re-index warning), extra watch folders (index or import)
- Private: local password, **copy** into ZipCrypto zip, optional `.ffpriv` disguise, Keep / Recycle Bin / Move originals
- Docs: `docs/LIBRARY.md`, `docs/LIBRARY_PRIVATE.md`, `docs/V0.6_COMPLETE.md`

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
