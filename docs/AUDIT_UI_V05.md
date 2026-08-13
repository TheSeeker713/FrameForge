# GUI audit — FrameForge v0.5 (CustomTkinter → Flet)

**Source of truth for current UI:** `src/frameforge/gui/app.py` (`FrameForgeApp`), plus `actions.py`, `shortcuts.py`, `exit_policy.py`, `tray.py`, `playlist_picker.py`, `queue_list.py`.

**Entry:** `python -m frameforge --gui` → `frameforge.gui.app.create_app()` → CustomTkinter `mainloop()`. Production launch: `start_worker=False`, `recover_on_launch=True` (pending only; no auto-start).

v0.5 replaces the CustomTkinter **window** with Flet. Backend (SQLite WAL worker, yt-dlp, ONNX, cookies, history) stays. Every command below must remain reachable after the rewrite (new chrome: header icons, hero, card overflow, floating bar, modals — not a 14-button toolbar).

## Layout today (must not be copied)

Permanent bottom toolbar with ~18 buttons. Error panel always visible. Auth/Settings sit in the URL row. Dark theme default. v0.5: light SaaS chrome; contextual actions only.

## Tabs

| Tab | Content |
|-----|---------|
| Queue | `QueueList` of live jobs (`list_jobs`, excludes `queue_hidden`) |
| History | Filters All/Completed/Failed, domain, search; re-download / clear |
| Thumbnails | Scrollable grid of cached thumbs |

## COMMANDS (must survive rewrite)

Machine-readable ids (tests parse the fenced list):

```
add_url
import_txt_md
download_selected
download_all_pending
pause_selected
resume_selected
cancel_selected
stop_after_current
retry_failed
upscale_selected
convert_mp3
select_recommended
set_format
clear_selected_queue
clear_finished_queue
open_folder
reveal_file
bump_priority
open_settings
authenticate_site
import_cookies_browser
import_cookies_txt
fail_pause_import_browser
fail_pause_authenticate
fail_pause_retry
fail_pause_skip_resume
fail_pause_stop
redownload_history
clear_history_selected
clear_history_all
playlist_enqueue_selected
quit_cancel_and_quit
quit_pause_and_quit
quit_wait_then_quit
tray_show
tray_pause_resume
tray_quit
tab_queue
tab_history
tab_thumbnails
shortcuts_help
```

## Command map (current → v0.5 surface)

| Id | Current control | v0.5 home |
|----|-----------------|-----------|
| `add_url` | Hero **Add** | Hero **+ Add to Queue** |
| `import_txt_md` | Hero **Import TXT/MD** | Hero outline **Import TXT/MD** → bulk confirm modal |
| `download_selected` | Bottom bar | Floating bar (selection ≥ 1) |
| `download_all_pending` | Bottom bar | Floating **More** or empty-state **Download** (must stay explicit) |
| `pause_selected` | Bottom bar | Card overflow / More |
| `resume_selected` | Bottom bar | Card overflow / More; tray Pause/Resume |
| `cancel_selected` | Bottom bar | Card overflow / More |
| `stop_after_current` | Bottom bar | More / overflow |
| `retry_failed` | Bottom bar (resets failed → pending, **does not arm**) | Failed card **Retry**; fail-pause modal **Retry this job** (modal path **does** arm that id) |
| `upscale_selected` | Always-visible bottom button | Floating bar **only if selection eligible**; card overflow |
| `convert_mp3` | Always-visible (enablement gated) | Floating bar **only if eligible**; card overflow |
| `select_recommended` | Bottom bar | Floating **More** |
| `set_format` | Bottom bar | Card overflow + More → Set format modal |
| `clear_selected_queue` | Bottom bar | More / overflow **Remove from queue** (DB only, no media delete) |
| `clear_finished_queue` | Bottom bar | More **Clear finished** |
| `open_folder` | Bottom bar | Card overflow |
| `reveal_file` | Bottom bar | Card overflow |
| `bump_priority` | Priority +/− | Optional More; not a primary CTA |
| `open_settings` | URL-row button | Header gear; **single instance** |
| `authenticate_site` | URL-row + error-panel button | Header shield; authenticate modal |
| `import_cookies_browser` | Auth dialog + error panel | Authenticate modal **Import from Firefox** |
| `import_cookies_txt` | Auth dialog | Authenticate modal **Choose cookies.txt** |
| `fail_pause_*` | Modal after bot/auth fail | Fail-pause modal (same five actions) |
| `redownload_history` | History bar | History action bar (new pending, no auto-start) |
| `clear_history_selected` / `clear_history_all` | History bar | History action bar (soft-hide) |
| `playlist_enqueue_selected` | Playlist picker | Playlist modal |
| `quit_*` | File→Quit / window X / tray Quit | Quit-while-busy 3-option modal |
| `tray_*` | pystray menu | Keep pystray if Flet has no tray |
| `tab_*` | CTkTabview + Ctrl+1/2/3 | Pill tabs Queue / History / Thumbnails |
| `shortcuts_help` | Help menu / F1 | Keep F1 / Settings help |

## Settings fields (must remain)

- Format preference (best / ≤1080p / ≤720p / ≤480p / audio)
- Upscale after download (still does not auto-start the download)
- Close to tray
- Fail-pause on bot-check / login (`fail_pause_on_auth`, default on)
- Gentle rate mode (`gentle_rate_mode`, default off)
- Resource monitor: enable, RAM %, CPU %, sustained seconds, auto-pause upscale
- Drop or demote: `ui_light_mode` (v0.5 is light-only)

v0.5 Settings cards: **Download & Quality** | **AI & Upscaling** | **System Behavior**.

## Dialogs

| Dialog | Notes |
|--------|--------|
| Settings | Must become single-instance (today: new `CTkToplevel` every click) |
| Authenticate site | Prefill domain/URL; Firefox import; cookies.txt; open browser |
| Playlist picker | Select all/none; enqueue pending only |
| Bulk import confirm | New vs duplicates; enqueue pending only |
| Set format | Radio: Best, ≤1080p, ≤720p, ≤480p, Audio-focused |
| Fail-pause | Five actions; after cookie import offer retry+resume |
| Quit-while-busy | Cancel+quit / Pause+quit / Wait then quit |
| Shortcuts help | F1 |

## Keyboard shortcuts (keep ids)

See `frameforge.gui.shortcuts.DEFAULT_SHORTCUTS` / [SHORTCUTS.md](SHORTCUTS.md). Bindings will move from Tk sequences to Flet keyboard events; action ids stay.

## Non-UI invariants (unchanged)

- Sequential: at most one of downloading / upscaling / converting
- Enqueue / import / playlist / crash recovery → pending; never arm
- Queue clear does not delete media; history v2 survives `queue_hidden`
- Worker off UI thread; marshal fail-pause + tray onto UI thread
- Thumb LRU cap 64
- Progress ticks update active row + status pill, not full list rebuild

## CTk modules after rewrite

Keep toolkit-agnostic: `actions.py`, `exit_policy.py`, `shortcuts.py` (registry), `tray.py`, `marshal.py`, `thumb_cache.py`.

Retire as primary window: `app.py` (CTk), `queue_list.py` (CTk rows), `playlist_picker.py` (CTk). Tests that instantiate `FrameForgeApp` migrate to `ui_flet` / headless bridge; do not drop coverage.

New package: `src/frameforge/ui_flet/` (theme, pages, components, bridge). Default `--gui` launches Flet only.
