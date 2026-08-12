# Performance & auto-start audit (v0.4.1)

Inspection of `main` as of this document. Ranked by likely user-visible impact. Line numbers refer to the tree at audit time.

## Ranked jank / CPU / RAM suspects

### 1. Full queue geometry rebuild every 1s (critical jank)

`FrameForgeApp._tick` (`src/frameforge/gui/app.py` ~1237–1248) always calls `refresh_queue()`, which:

1. `repo.list_jobs()` with **no status filter** — entire `jobs` table (`repository.py` ~180–190).
2. `QueueList.update_jobs` (`queue_list.py` ~182–214) for **every** row:
   - `pack_forget()` then `pack()` (Tk geometry on the scrollable canvas).
   - `label.configure` / `badge.configure` / `fg_color` even when text is unchanged.
   - `on_selection_changed` → error panel + convert-button sync.
   - `self.after(1, restore_scroll)` extra main-thread callback.
3. `refresh_history()` — second full query + second `update_jobs`.
4. `refresh_thumbnails()` — scans all jobs for thumb files (`thumbnails.py` ~80–88).

**Why drag is delayed:** window-move already stresses the Win32/Tk geometry manager. Re-packing dozens/hundreds of CTk frames every second fights the drag. This is the primary jank suspect.

Progress lives in SQLite (`update_progress` from the worker thread). The UI only sees it because `_tick` rebuilds the whole list. Progress is therefore coupled to a full rebuild.

### 2. Main-thread network / decode on Add URL (freeze, not drag)

`add_url` → `_enqueue_single_url` (`app.py` ~541–553):

- `probe_listing_bundle` runs **yt-dlp `extract_info`** on the Tk thread (`metadata.py` ~40–41).
- `cache_job_thumbnail` **HTTP-fetches** the thumbnail on the Tk thread (`thumbnails.py` ~91–108).

Playlist URLs also call `extract_playlist` on the Tk thread (`app.py` ~528–530).

These do not start media downloads, but they block the UI and can look like “the app started working.”

### 3. Thumbnail decode on the main thread; unbounded cache

- Queue row thumbs: `QueueList._thumb_image` (`queue_list.py` ~119–137) uses PIL `Image.open` on first sight; `_thumb_cache` is an **unbounded** `dict[str, CTkImage]`.
- `_apply_thumb` still `Path.is_file()` every row every refresh (`queue_list.py` ~139–146).
- Thumbnails tab: `refresh_thumbnails` (`app.py` ~1052–1089) re-`Image.open`s when the signature changes; no LRU. Called from every `refresh_queue`.

### 4. Chatty SQLite on the UI timer

Every 1s while the window lives:

- `SELECT * FROM jobs` (queue).
- History `list_history`.
- `list_thumbnail_jobs` walks every job and `Path.is_file`.
- `_poll_resources` → `settings_from_repo` (several `get_setting` queries) even when not upscaling (`app.py` ~1217–1223).
- Per-row `job.site_key` / `upscale_recommended` / `options()` JSON parse.

Worker progress writes (separate thread) are fine; the UI read amplification is the problem.

### 5. Worker poll 20 Hz when armed (CPU, not Tk)

`SequentialWorker.poll_interval = 0.05` (`pipeline/__init__.py` ~30, `worker.py` ~38, ~243). When **disarmed**, the loop still sleeps 50ms if the thread was started. GUI launch does **not** start the thread today.

`worker.events` is an **unbounded** list (`worker.py` ~45, appends in `_run_*`).

### 6. Resource monitor on the Tk timer

`_poll_resources` runs on `_tick` (main thread). `psutil.cpu_percent` / `virtual_memory` are cheap; reloading settings and calling `maybe_auto_pause_upscale` every second is unnecessary when idle. UI banner is updated even when the warning text is unchanged.

### 7. No timer hygiene

- Interval is always 1000ms; no idle vs active split (`app.py` ~1248).
- No skip when `withdraw()` to tray.
- `_tick` is not cancelled in `shutdown` (`app.py` ~1250+); `_shutting_down` only short-circuits the body.

---

## Auto-start: confirmed vs suspected

### Confirmed: GUI launch does **not** arm the worker

- `create_app()` / `python -m frameforge --gui` → `FrameForgeApp(start_worker=False)` (`__main__.py` ~38, `app.py` ~29–32, ~246–247).
- `build_worker` does not call `start()` (`pipeline/__init__.py` ~26–38).
- Enqueue, bulk import, playlist `enqueue_selected`, cookie import do not call `request_download_*`.
- Worker claims only while `_armed` (`worker.py` ~108–120, ~146–161, ~287).

This matches the v0.2 / Tier 1 “manual start” design. A **fresh** process should sit idle with pending jobs.

### Suspected user-visible “it started by itself”

1. **Stuck `downloading` / `upscaling` rows after a crash.** Launch does **not** call `recover()`. Those rows stay `downloading` in the UI (progress bar looks live) even though no worker thread is running. Clicking **Download all pending** then calls `recover()` (`worker.py` ~151) which resets interrupted jobs to `pending` **and** arms the worker for **all** pendings — the whole queue runs. That is easy to read as “it auto-processed the queue.”
2. **Add URL blocking** (yt-dlp probe + thumb HTTP) feels like a download starting.
3. **`upscale_after_download` setting** only matters after an explicit download; it does not arm on launch.
4. Older builds historically defaulted `start_worker=True` (`docs/AUDIT_v0.1.0.md`). Current `main` does not.

**B1/B2 intent:** keep launch idle; recover interrupted jobs to pending **without** arming; never claim until Download selected / Download all / explicit Resume.

---

## Recommended fixes (impact order)

1. **Idle launch + recover-without-arm** — recover interrupted stages on GUI init; do not `start()`/`request_download_all()`. Tests: enqueue stays pending; leftover pending + crashed downloading do not start.
2. **Decouple progress from full rebuild** — `refresh_progress()` updates bar + one row; full `update_jobs` only on structural change or a slower cadence. Skip `pack_forget` when id order is unchanged.
3. **Timer hygiene** — idle interval ~2.5s; active progress ~400–500ms; skip when withdrawn; cancel `after` on shutdown.
4. **Thumb LRU + skip redundant work** — bound cache; do not `Image.open` on cache hit; do not refresh thumb tab off-screen every tick.
5. **Bound `worker.events`**; stop reloading monitor settings every tick; update resource banner only on change.
6. **Optional light UI** — setting `ui_light_mode` skips live thumbs / uses slower refresh.

Do **not** enable concurrent media downloads. Worker and tray must keep using `after(0, …)` for GUI mutations (`marshal_ui`, `TrayService.marshal`).
