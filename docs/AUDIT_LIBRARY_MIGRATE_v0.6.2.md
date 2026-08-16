# AUDIT — Library migrate 1-file abort + download-root init (v0.6.2)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-16 |
| **Audited commit** | `941c45346c51a0d84010bddf1a561ce299e0e802` (v0.6.1) |
| **Branch** | `main` |
| **Package** | 0.6.1 (`src/frameforge/__init__.py`) |
| **Auditor** | Cursor agent — code + live tree/DB snapshot + reproduced abort. **No media was moved or deleted.** |

Field report: Library “move videos” starts, progress appears, then **stops after one file**. Init did not organize `youtube\` thumbs. Layout looks partial (`database/`, `temp/`, `cookies/`, `videos/`, `youtube/`).

---

## Executive summary — abort cause (named)

**The batch dies when `on_progress` (or `between_files`) raises, not when a per-file `shutil.move` fails.**

`run_library_move` only wraps the move/index call in `try/except`. Progress and the between-files hook sit **above** that try. Any exception there unwinds the whole function after file 1 has already been transferred.

`LibraryMoveRunner._run` then **throws away** the in-progress report (`moved=1`, remaining files still queued) and replaces it with `MoveReport(failed=1)`. The UI can show a single failure while one file sits in Library and the rest remain in `youtube\`.

This was reproduced (traceback below). It matches the live disk state: **exactly one** video in `K:\…\Uncategorized\`, 57 indexed paths missing, 75 videos still under `Downloads\FrameForge\youtube\`.

This is **not** “eligibility of 1.” A read-only replay of today’s DB + disk scan yields **98** candidates (11 jobs + 87 loose videos). Progress would read **Moving 1 of 98**, then stop — the reported symptom.

Per-file `OSError` from cross-drive `shutil.move` is already caught and would **continue**. It is **not** the abort. Cross-drive copy without verify+unlink is still a reliability gap (Phase 1).

---

## A. Migrate path

### A.1 Entry (Move click → worker)

| Step | Location |
|------|----------|
| Button | `onboarding_dialog` / `new_downloads_dialog` → `FrameForgeUi.confirm_library_move` |
| Handler | `src/frameforge/ui_flet/app.py` `confirm_library_move` (line 1344) |
| Dialog | `open_library_onboarding(..., replace=True)` so the wizard shows the progress column |
| Worker | `LibraryMoveRunner.start` → daemon thread `frameforge-library-move` |
| Work | `run_library_move` in `src/frameforge/library/mover.py` |
| Per file | `move_into_library` / `move_path_into_library` in `src/frameforge/library/ingest.py` |

The worker opens its **own** `JobRepository` + `LibraryStore` on `db_path` (`check_same_thread=False`, timeout 60s). Sequential download worker is untouched.

### A.2 List builder (jobs ∪ disk)

Built **once** on the UI thread in `confirm_library_move`, then passed in:

1. **Jobs:** `completed_jobs_not_in_library` (`ingest.py` 35–47)
   - `jobs.status = completed` with a live `download_path` / `output_path` file
   - **Skipped** if `library_items` already has that `job_id` **or** that path — even when the indexed path is missing on disk
2. **Disk:** `download_videos_not_in_library` (`scan.py` 109–147)
   - Roots: `_migrate_disk_roots()` → production `[frameforge_root()]` = `%USERPROFILE%\Downloads\FrameForge`
   - Tests / FakePage: **empty** unless `ui._library_scan_roots` is set (does not scan the user’s Downloads)
   - Recursive `rglob`; skip relative dirs in `DOWNLOAD_SCAN_SKIP`: `models`, `temp`, `cookies`, `archive`, `thumbnails`, `database`, `Private`
   - **Not skipped:** `youtube/`, `x.com/`, `videos/`, `downloads/`, `samplelib.com/`, **`upscaled/`**
   - Suffixes: `VIDEO_SUFFIXES` in `library/paths.py` (`.mp4 .mkv .webm .mov .avi .m4v .wmv .mpeg .mpg`)
   - Skip `.part` (suffix is `.part`, not a video suffix)
   - Skip files already under `library_root`; skip paths already in `library_items`

Dedup: disk paths whose `resolve()` matches a job media file are dropped in `run_library_move` (lines 94–113).

**Live eligibility (copied DB, no writes to user media), 2026-08-16:**

| Set | Count |
|-----|-------|
| `completed_jobs_not_in_library` | 11 |
| `download_videos_not_in_library` (`frameforge_root()`) | 87 |
| Union passed to the worker | **98** |

Disk sample includes `youtube\*.mp4`, `samplelib.com\`, and `upscaled\job1_*.upscaled.mp4` (test clips — scan does not exclude `upscaled/`).

### A.3 Per-file operation

```77:78:src/frameforge/library/ingest.py
        dest = unique_dest(folder, src.name)
        shutil.move(str(src), str(dest))
```

Same for loose files (`move_path_into_library` line 124). **No** explicit copy2 → size verify → unlink.

- **Same volume:** `os.rename` inside `shutil.move`.
- **Cross volume (this machine):** `os.rename` raises `OSError` (EXDEV); `shutil.move` falls back to copy + unlink. No size check. No `\\?\` long-path prefix. `unique_dest` does **not** strip remaining illegal Win32 filename chars (relies on yt-dlp sanitization).

Destination: `store.ingest_dir()` = `{library_root}/Uncategorized`.

**Live `library_root`:** `K:\JEREMY'S FILES\video` — a **bare pick**, not `<pick>/FrameForge/Library`. `set_root` in v0.6.1 would rewrite new picks; this setting predates that contract (or bypassed it). Destinations therefore land in `K:\JEREMY'S FILES\video\Uncategorized\`, not `…\FrameForge\Library\Uncategorized`.

**Cross-volume:** download tree is `C:\Users\jroba\Downloads\FrameForge` (C: ~198 GB free); library is `K:` (~3046 GB free). Confirmed `cross_volume True`.

### A.4 Why it stops after 1

#### Ruled out

| Hypothesis | Why not |
|------------|---------|
| Eligibility is only one file | Union is **98** today; youtube still has **75** videos |
| Per-file `shutil.move` / DB `IntegrityError` | Inside `try` at `mover.py` 139–152; would increment `failed` and continue |
| Unique `library_items.path` / partial unique `job_id` | Same — `sqlite3.IntegrityError` is `Exception` |
| Dialog `wire_closable` cancelling the token | `library_onboard` is **not** wired closable (`dialog_host.py` 72–75). `start()` also `cancel.clear()` |
| `repair_frameforge_tree` aborting the worker | Init-only; not on the move path |

#### Named cause (reproduced)

`on_progress` / `between_files` are **outside** the per-file try:

```131:134:src/frameforge/library/mover.py
        if on_progress:
            on_progress(progress)
        if between_files is not None:
            between_files(job if job is not None else path)
```

GUI progress:

```1371:1372:src/frameforge/ui_flet/app.py
        def on_progress(progress: MoveProgress) -> None:
            self._marshal_ui(lambda: self._apply_move_progress(progress))
```

`_marshal_ui` (1247–1267): prefers `page.run_task` (Flet 0.86 `asyncio.run_coroutine_threadsafe`, fire-and-forget). **If `run_task` raises**, it **falls through to `fn()` on the worker thread**. `_apply_move_progress` wraps only `page.update()`; assignments to `_move_status.value` / `_move_file.value` / `_move_bar.value` are unprotected. After `open_library_onboarding(replace=True)` rebuilds the wizard, those Flet controls can raise on the **second** tick (file 2), once file 1 is already on disk.

The runner then **discards** the real report:

```233:234:src/frameforge/library/mover.py
            except Exception as exc:  # noqa: BLE001
                report = MoveReport(failed=1, errors=[str(exc)])
```

`log.warning` for per-file failures has **no** `exc_info=True`. The runner path logs nothing (`exc` is swallowed into a one-line error string). There is no per-file src/dst success log.

#### Reproduced traceback (isolated 3-file batch, 2026-08-16)

`on_progress` raised `RuntimeError("simulated UI/progress failure on file 2")` after file 1 moved:

```
Traceback (most recent call last):
  File "…\tmp_audit_inspect.py", line 138, in reproduce_progress_abort
    run_library_move(repo, store, on_progress=boom)
  File "D:\_Dev\Projects\FrameForge\src\frameforge\library\mover.py", line 132, in run_library_move
    on_progress(progress)
  File "…\tmp_audit_inspect.py", line 135, in boom
    raise RuntimeError("simulated UI/progress failure on file 2")
RuntimeError: simulated UI/progress failure on file 2
```

| After abort | Result |
|-------------|--------|
| `a.mp4` | **Moved** into Library `Uncategorized` |
| `b.mp4`, `c.mp4` | **Still in source** (never attempted) |
| `LibraryMoveRunner.report.moved` | **0** (discarded) |
| `report.failed` | **1** |
| `report.errors` | `['simulated UI/progress failure on file 2']` |

Same shape as the field report: one file transferred, batch gone, summary looks like a single failure.

#### Field corroboration (read-only)

| Check | Value |
|-------|--------|
| SQLite | `C:\Users\jroba\Downloads\FrameForge\database\frameforge.db` (532 480 bytes) |
| `library_onboarded` | `'1'` (marked complete despite incomplete collection) |
| `library_items` | 58 rows; **1 path exists**, **57 missing** |
| `K:\JEREMY'S FILES\video\Uncategorized` | **1 file:** `Agentic AI – Complete Course for Beginners [Zy7EXDONlTY].mp4` (**4 481 858 171 bytes ≈ 4.48 GB**) |
| `Downloads\FrameForge\youtube\` | **75** videos, **56** thumbs beside them, **15** `.part`/`.ytdl`/`.temp` |
| Completed jobs with a file still on disk | 12 (11 not linked to `library_items`) |
| `v061_layout` (`…/FrameForge/Library`) | **False** |

Sequence that fits both the code and the disk:

1. User clicks Move. Worker starts a **98-file** (or similar) batch. Progress: *Moving 1 of N…*
2. File 1 is a **4.5 GB cross-drive copy** (`C:` → `K:`). The bar stays on 1 until `shutil.move` returns (can look frozen).
3. File 2: `on_progress` runs **before** the next move. An exception here **kills the thread work** via A.4. Files 2…N never run. Report rewritten to `failed=1`.
4. `completed_jobs_not_in_library` will not retry the 58 already-indexed jobs (including 57 missing K: paths). A later Move relies on the disk scan of `youtube\`.

`list_playable_items` only shows rows whose file exists, so the grid can show **one** playable card while 75 downloads remain on C:.

### A.5 Logging gaps

| Event | Today |
|-------|--------|
| Success (src, dst) | **Not logged** |
| Per-file failure | `log.warning("Library move failed for %s (%s): %s", ident, label, exc)` — **no traceback**, no src/dst |
| Progress-callback abort | Runner replaces report; **no** `log.exception` |
| Migrate report file | **None** (only `MoveReport.errors` strings, max 3 shown in the wizard) |

Phase 1 must log each file `src → dst → ok|fail` and `log.exception` on callback/runner abort, and keep the in-progress `MoveReport`.

---

## B. Init / folder repair

### B.1 What runs on `--gui` / start

`FrameForgeUi.__init__` and `python -m frameforge --gui` call `ensure_output_tree()` (`paths.py` 94–102):

1. Create `Downloads\FrameForge\` plus `SUBDIRS`: `downloads`, `upscaled`, `converted`, `temp`, `models`, `archive`, `cookies`, `thumbnails`, `database`, `videos`
2. `repair_frameforge_tree(frameforge_root())` (`layout.py` 56–84)

Library pick (`LibraryStore.set_root`) also runs `resolve_library_home` → `ensure_library_tree` and repairs the **library** FrameForge folder — not the download `youtube\` tree. Repair is **synchronous on the UI thread** (can stall startup if the root is huge; today it only `iterdir()`s immediate children, so it is fast — and incomplete).

### B.2 Which roots are scanned

**Only loose files that are immediate children of the FrameForge root.** Not recursive. Not `youtube/`, `x.com/`, `videos/`, `downloads/`, `samplelib.com/`.

### B.3 Why thumbs still sit beside mp4s in `youtube\`

`repair_frameforge_tree` skips directories:

```69:71:src/frameforge/layout.py
    for child in list(root.iterdir()):
        if not child.is_file():
            continue
```

Live: `thumbnails\` already has **109** queue-id thumbs (`1.jpg`, `1.webp`, …). `youtube\` still has **56** sidecar `*.webp`/`*.jpg` next to videos. Init never looks there. Policy in this audit (Phase 2): **keep per-site folders as media homes**; move only loose thumbs/db/junk candidates.

### B.4 Where the DB lives vs `database\`

| Path | State |
|------|--------|
| `Downloads\FrameForge\database\frameforge.db` | **Live DB** (`paths.db_path()`, 532 480 bytes) — app uses this |
| `Downloads\FrameForge\frameforge.db` | **Absent** |
| `frameforge.db.broken`, `frameforge.db.corrupt-20260815-171152`, `frameforge.dump.sql` | Leftovers at **root**; repair only matches exact `frameforge.db` / `-wal` / `-shm` names, so these stay |

If both root `frameforge.db` and `database\frameforge.db` existed, `_safe_move` **skips when dest exists** — risk of opening an empty new DB while data stays at root. Not the current field state.

---

## C. Library UI after partial migrate

### C.1 Count / grid / play vs disk

`refresh_library` binds `list_playable_items` (`scan.py` 75–83): heal missing paths **only under `library_root`**, then keep rows whose `Path.is_file()`. Toolbar count = visible cards.

Heal does **not** search `Downloads\FrameForge\youtube\`. So 57 rows pointing at missing K: paths stay hidden; 75 youtube files are not cards. Play (`os.startfile`) only runs for playable rows — the one 4.5 GB file on K: can play; the rest cannot from Library.

### C.2 Do `library_items` rows point at valid paths?

**1 of 58 yes.** Examples of missing rows (still in SQLite):

- `K:\JEREMY'S FILES\video\Uncategorized\Just Asking Questions： Today's Top Conspiracies (Episode 640) [YIVOwW4HtSs].mp4`
- `K:\JEREMY'S FILES\video\Uncategorized\The Basement： Travis Taylor ｜ Physics of Skinwalker Ranch [sm7coKl6Ko0].mp4`

Names use fullwidth `：` (U+FF1A), which NTFS allows. The abort is not “illegal colon on file 2”; those files were indexed (DB write after a successful `dest.is_file()` at the time) or the path was recorded when the file later vanished. Either way, **retry is blocked for those job_ids** until index rows are healed or reset.

`library_onboarded=1` so onboarding will not force another Move; the user must use “N new downloads” / Import. That prompt uses the same worker, so the same abort can repeat.

---

## Phase 1–3 implications (do not treat as shipped)

1. **Worker:** wrap `on_progress` / `between_files` / final progress in try/except; **never** replace an in-progress `MoveReport`; `log.exception` on runner abort; log src/dst/result per file.
2. **Transfer:** same-drive `move`; cross-drive **copy2 → verify size → unlink**; fallback if `move` raises `OSError`.
3. **Eligibility:** keep jobs ∪ recursive video scan; skip already-indexed **live** paths; skip `.part`; do not stop the batch on file 2 failure (tests: error on file 2 still completes file 3+).
4. **Dest contract:** `<pick>/FrameForge/Library/Uncategorized`; never a bare folder. Existing `K:\JEREMY'S FILES\video` should be migrated onto that contract on next pick/repair.
5. **After migrate:** refresh grid; auto `scan_library_folder` for orphans under the library tree.
6. **Init:** background recursive thumb/db sweep of all site folders; junk candidates listed, not auto-deleted; keep site folders for media.
7. **Onboarded:** do not set complete unless migrate finished or user Skip (already the intent; field `onboarded=1` with 57 missing paths means Skip or a false “nothing remaining” after the discarded report).

---

## Acceptance mapping (this audit only)

| Check | Result |
|-------|--------|
| Audit names exact abort reason | **PASS** — uncaught `on_progress`/`between_files` + runner discarding `MoveReport` (`mover.py` 132 + 233–234). Reproduced traceback above. |
| Move 20+ files / progress / grid / init repair | **Not claimed.** Phase 1+ |

No migrate “fix” is included in this document’s commit.
