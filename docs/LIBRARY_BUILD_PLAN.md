# Library build plan

Status: waiting for a go before Phase 1.
Branch: `library-build` (created from `main` at `087d2d1`, v0.6.38). Not pushed.
Schema today: version 4 in `schema_migrations`. This build adds version 5.

## Local work

`git status` lists many modified files. `git diff` and `git diff --ignore-cr-at-eol` are empty for all of them. They are line-ending noise, not Library edits. `git stash list` is empty. There is no unpushed commit: `main` and `origin/main` are both `087d2d1`.

Do not commit those dirty files. They are not part of this build.

Committed Library behavior this plan builds on (do not revert):

- Books and folders are SQLite links. `library/books.py` classifies a path and title into Movies, TV Shows, YouTube, Facebook, X, TikTok, Instagram, Porn, or Other Videos, plus a folder. A leading number such as `300` is not a season.
- Adding a video calls `link_files` / `publish_completed_downloads` and then `_file_in_book`. The video file is not moved.
- The Library tab paints `library_browser` only. `library_stack` does not mount `library_grid` or the WebGL host. `_sync_library_surface` keeps the WebView overlay off.
- `library_browser.data` is the contract tests assert: `kind=library_books`, `book`, `folder`, `books`, `folders`, `clips`, `catalog`.

## Conflicts

1. `AGENTS.md` says commit and push `main` after every step. This build says never push `main`, never force-push, and do not touch draft PR #2. This build follows that. Commits stay on `library-build`.
2. `docs/LIBRARY_DESIGN_FEEDBACK.md` describes a WebGL cover-flow shelf and says not to implement. This build uses native Flet and does not start the WebGL shelf or the WebView2 surface. The feedback notes that still apply: polished cards, sorting, albums as database links, files stay at the source path.
3. The prompt names the download folder as `K:\JEREMY'S FILES\downloads`. The app uses `downloads_dir()`, which is the folder chosen at onboarding (often `<FrameForge home>/downloads`). Nothing in this build hardcodes a drive letter. Scan and watch folders use `downloads_dir()`, `upscaled_dir()`, and `library_watch_folders`.
4. `library/actions.py` `play_library_item` opens the OS player. `ui_flet/app.py` `play_library_item` opens the in-app dialog. Phase 7 renames the OS helper to `open_library_item_externally` and updates callers. The in-app method keeps its name.
5. `enqueue()` takes a URL, not a local path. A linked item with no `job_id` cannot be upscaled through `request_upscale_ids` today. Phase 2 leaves that button disabled with the tooltip "Upscale needs a queue job for this file" unless a local-path queue path already exists. No new upscale pipeline work.

## Baseline tests

Command: `pytest -q -p no:cacheprovider --timeout=120` on `library-build` at `087d2d1`, before any Phase 1 code.

Result, recorded 2026-10-09: **7 failed, 689 passed, 1 skipped** in 410 s (exit code 1).

Failures already on `087d2d1`, before this build:

- `tests/test_completed_thumbnails.py::test_handler_stores_thumb_from_sidecar`
- `tests/test_cookie_auto_resume.py::test_validated_cookies_retry_without_a_dialog`
- `tests/test_library_studio_embed.py::test_webview_loads_embed_without_attaching_to_another_frameforge`
- `tests/test_shell_safety.py::test_production_ui_has_no_forbidden_shell_apis`
- `tests/test_transport_fail_pause.py::test_unknown_fail_on_first_does_not_claim_second`
- `tests/test_transport_fail_pause.py::test_handler_failed_without_raise_still_halt_bulk`
- `tests/test_ytdlp_parity.py::test_handler_stores_invocation_snapshot`

`test_transport_fail_pause` stays as it is. That is a separate decision. `test_shell_safety` and the studio embed test are in Phase 8. The thumbnail, cookie, and yt-dlp failures are baseline noise. Later phases must not add failures beyond this list. The yt-dlp failure compared a temp download folder with the onboarded downloads folder. This build does not change that path.

## What the finished Library looks like

```
+----------------+----------------------------------+----------------------+
| Sidebar 240px  | Toolbar                          | Detail 360px         |
|                | search, sort, size, add, refresh | hidden until a card  |
| All            +----------------------------------+ is selected          |
| Recent         |                                  |                      |
| Favorites      | Thumbnail grid (paged)           | thumb, title         |
| Watch later    | 16:9 cards, title, duration,     | source URL           |
| Books          | resolution, version badges       | versions             |
|   folders      |                                  | job, organize        |
| Albums         |                                  | actions              |
| Sites          |                                  |                      |
| Watch folders  |                                  |                      |
+----------------+----------------------------------+----------------------+
```

The player replaces the grid column. Esc or Back returns to the same selection. The WebGL shelf stays in `design/library-studio/` and is not started.

## Schema (migration 5)

`migrate()` keeps `schema_migrations`. No `PRAGMA user_version`. SQL for version 5 uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`. `ALTER TABLE ... ADD COLUMN` is not inside `executescript`, because a second run would fail. A `POST_MIGRATE` hook runs after the SQL for that version and adds each column only when `PRAGMA table_info` does not already list it.

Before the hook runs, copy the database file to `<db>.bak-v4` when the applied version is 4 and the backup is missing.

New columns on `library_items`: `source_url`, `source_site`, `primary_file_id`, `duration_ms`, `file_size`. Existing `path` and `thumb_path` stay and always match the primary file, so current tests keep working.

New tables: `library_files` (original, upscaled, linked) and `library_thumbs` (ok, miss, pending), as specified in the build prompt. Unique index on `library_files.path`.

`library/versions.py` owns "primary = the best present file" and writes `path`, `primary_file_id`, `width`, `height`, `duration_ms`, and `file_size` on `library_items` whenever files change. Best means the highest-resolution present upscale, else the original or linked file.

Backfill in the Python hook, no ffprobe:

- One `library_files` row per item. `role=original` when `job_id` is set, else `linked`. Set `primary_file_id`.
- If the job URL starts with `http://` or `https://`, copy it to `source_url`. `source_site` is the host with a leading `www.` removed. Reject `javascript:`, `file:`, and empty.
- If a completed job has an `output_path` that differs from `download_path` and the file exists, add `role=upscaled` on the same item. Read scale from the file name or job options when present.
- If `thumb_path` exists on disk, insert `library_thumbs` with `status=ok`.

Store methods: `list_files`, `add_file`, `get_file_by_path`, `set_file_probe`, `mark_file_missing`, `primary_file`, `query_items`. `query_items` uses SQL `ORDER BY`, `LIMIT`, `OFFSET`, and parameterized `LIKE`. Search matches title, site, source URL, and file name. It returns the page and a total count.

## Modules

| Piece | Where |
| --- | --- |
| Migration 5 and backup | `db/migrate.py` |
| `LibraryFile`, `LibraryThumb`, new item fields | `library/models.py` |
| Queries and file rows | `library/store.py` |
| Primary-file rule | `library/versions.py` |
| ffprobe, never raises, NULL duration when missing | `library/probe.py` |
| Download and upscale ingest | `library/ingest.py`, one try/except hook in `upscale/handler.py` after `set_paths` |
| `upscaled/` is a version when the stem matches, else its own linked item | `library/scan.py` |
| Thumbnail cache and worker | `library/thumbs.py`, `library/thumb_worker.py`, `download/thumbnails.py` |
| Sidebar, grid, detail | `ui_flet/components/library_sidebar.py`, `library_grid.py`, `library_detail.py` |
| Books section of the sidebar | `ui_flet/components/library_browser.py` keeps the `library_books` data contract |
| Player view | `ui_flet/components/player.py` |
| Open, reveal, trash | `util/reveal.py` or `util/platform_open.py`, `util/recycle.py` |
| Tab layout | `ui_flet/app.py` |

## Thread model

The Flet event handler only reads a page of rows and builds controls. It does not run ffmpeg, ffprobe, a directory walk, a network call, or a bulk write.

- Probe and thumbnail work run on `ThumbWorker` (`ThreadPoolExecutor`, 2 workers, or 3 when `os.cpu_count() >= 8`). Visible grid files are first. Each worker opens its own SQLite connection. It does not use the UI connection.
- Finished thumbs are batched about every 250 ms. The UI applies them with `page.run_task` on an async handler and `control.update()` on the changed cards. No full `page.update()` from a worker. Sync work uses `page.run_thread`.
- `refresh_library` stops calling `ensure_library_thumbnail` inline. Misses live in `library_thumbs` (`status=miss`) and are not retried until the cache key changes or the user chooses Regenerate thumbnail.
- Cache key is `sha1(abs_path|size|mtime_ns|v1)`. Files live at `<app data>/thumbnails/library/<key[:2]>/<key>.jpg`. A source and its upscale do not share a thumb.
- Still extraction seeks with `-ss` before `-i`, uses `thumbnail=24,scale=480:-2`, checks black frames with Pillow, and passes `CREATE_NO_WINDOW`. Timeout 20 s. Never raises.
- `prune_thumb_cache(max_bytes=2 GiB)` runs at startup on a worker.

## UI behavior to keep correct

- Single click selects and opens the detail panel. Double click plays in the app. Right click is a `ContextMenu`.
- Grid is `ft.GridView` with `build_controls_on_demand=True`. First load is 300 rows from `query_items`. `on_scroll` appends the next 300. Filter, sort, or search resets to page 1 and calls `grid.update()` only.
- Keyboard goes through the existing `page.on_keyboard_event`. Log the raw `e.key` strings once on Windows and match those labels. Player keys are handled only while the player is open, so Esc still closes dialogs the way it does now when the player is closed.
- flet_video 0.86.5 methods `stop`, `play`, `pause`, `seek`, and `jump_to` are async. The current `video.stop()` in `player.py` does not run. The rewrite awaits them.
- Player is a view over the grid column, `fit=CONTAIN`, no fixed 16:9. Playlist holds present versions. Switch calls `jump_to` then seeks to the saved position.
- Remove from Library deletes rows only. Delete file uses the Recycle Bin or Trash, asks first, and never calls `unlink`. `send2trash` on macOS and Linux. Windows keeps the existing `SHFileOperationW` path. Delete is not tied to `reveal_launch`.
- Open and reveal build argv in one function so tests can check `win32`, `darwin`, and `linux` without launching. Windows reveal is `["explorer", "/select,", path]` with `/select,` as its own argument. Explorer's exit code is ignored.

APIs re-checked in the installed flet 0.86.5 and flet_video 0.86.5: `GridView` fields named in the prompt, `ContextMenu.secondary_items`, `GestureDetector`, `KeyboardListener`, `UrlLauncher`, `VideoConfiguration.hardware_decoding_api` and `mpv_properties`, `MaterialDesktopVideoControls.bottom_button_bar`, and async `Video.stop` / `play`.

## Phase order

Phase 1 data model, Phase 2 ingest and versions, Phase 3 thumbnail worker, Phase 4 grid and sidebar, Phase 5 detail panel, Phase 6 player, Phase 7 open, reveal, and trash, Phase 8 packaging and dead shelf code, Phase 9 tests, Phase 10 report. Each phase gets its own commit on `library-build`. The next phase starts only after that phase's checks pass.

Out of scope stays out of scope: upscale mux and color bugs, packaged yt-dlp invocation, draft PR #2, and `gui/app.py`.

## Done for this document

The plan is written. The baseline line above is filled before Phase 1. No Phase 1 code until Jeremy says go.
