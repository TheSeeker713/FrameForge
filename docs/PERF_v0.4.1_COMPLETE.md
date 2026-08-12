# v0.4.1 performance & auto-start gate

**Package version:** 0.4.0 (unchanged)  
**Pass:** performance / memory / idle-launch (documented as v0.4.1)  
**Suite:** `python -m pytest -q` → **233 passed / 0 skipped / 0 failed**

Sequential single-active media stage is unchanged. Enqueue still does not start downloads. Pause/resume, quit policy, tray, site folders, cookies, playlists, convert, and shortcuts are preserved.

## Auto-start fixed

- Production GUI (`create_app()` / `python -m frameforge --gui`) never arms the worker.
- `prepare_idle_launch()` recovers crashed `downloading` / `upscaling` / `converting` rows to pending and **does not** `start()` or `request_download_all()`.
- Enqueue, bulk import, playlist enqueue, and browser cookie import stay pending until **Download selected**, **Download all pending**, or an explicit resume of work.

Tests: `tests/test_gui_idle_launch.py`, `tests/test_startup_no_autodrain.py`.

## Refresh strategy

- Progress ticks update the progress bar and the **active queue row only** (`refresh_progress` / `QueueList.update_one_job`).
- Full `update_jobs` runs on structural changes (add/cancel/status/order) or every 5 armed ticks.
- `pack_forget`/`pack` is skipped when the job id order is unchanged.
- History and Thumbnails tabs are not rebuilt every tick unless that tab is selected.
- Idle **2500 ms**, armed **400 ms**, tray **2000 ms**. Tick is cancelled on shutdown. Withdrawn (tray) windows skip queue geometry work.

Tests: `tests/test_gui_progress_refresh.py`, `tests/test_gui_timer_hygiene.py`.

## Thumb cache

- `frameforge.gui.thumb_cache.LruCache` bound to **64** decoded `CTkImage`s.
- Cache hit does not reopen the file. Placeholders first; decode on first path apply.
- Light UI (`ui_light_mode=1` in Settings) disables live thumbs and uses 4000/1000 ms ticks.

Tests: `tests/test_thumb_lru.py`, `tests/test_ui_light_mode.py`.

## Memory / monitor / thread safety

- Worker event log capped at 200; error panel at 8000 characters.
- Resource monitor: settings reload ≤ every 10 s; banner updates only on text change; samples do not rebuild the queue.
- Tray and worker UI callbacks go through `schedule_on_ui` → `after(0, …)`.

Tests: `tests/test_memory_bounds.py`, `tests/test_resource_poll_cost.py`, `tests/test_gui_marshal.py`.

## Audit

Inspection and ranked suspects: [AUDIT_PERF_v0.4.1.md](AUDIT_PERF_v0.4.1.md) (includes **Fixes applied**).
