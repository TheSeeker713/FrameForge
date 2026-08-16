# Full project field audit — v0.6.3 (no code changes)

**Date:** 2026-08-16  
**Package:** 0.6.3 (`c6ccbef`)  
**Machine:** live `%USERPROFILE%\Downloads\FrameForge\` + `K:\JEREMY'S FILES\video`  
**Method:** read-only DB/disk/log inspection + code trace. No product code, schema, UI, or version changes in this pass. User media was not moved.

---

## 1. Executive summary

**Library Move does not fail on file 2.** The only field log from this tree (`temp\library_move_20260816_102055.log`) starts a batch of **81 files** (`jobs=11 disk=70`) and never writes `OK`, `FAIL`, or `ABORT`. The worker is inside **file 1**: a **cross-drive `shutil.copy2` of 4,481,858,171 bytes** with **no per-byte progress and no cancel check during the copy**.

That file is always the same because `list_jobs("completed")` is `ORDER BY priority DESC, id ASC`, and the first completed job whose path still exists on disk is always **job 2** (jobs 3 and 23 are duplicate rows of the same path). Copy never finishes (quit joins only **2.5s**, then kills the process), so job 2 stays eligible forever. The progress bar showing “Agentic AI…” then freezing is the copy, not a 1-item list.

v0.6.2 (callback-outside-try) and v0.6.3 (stale `library_items` purge) do not apply here: **`library_items` is already empty** (`purged_missing=0`), and the log has **no exception on file 2**.

**Reset Library onboarding** vanishes because `DialogHost` allows only one dialog: Settings close fires `on_dismiss=cancel` → `close_dialog()`, which closes the reset dialog that just replaced Settings. `wire_closable` also forces the reset dialog `modal=False`. The reset handler itself is fine; the user never gets to click it. Tests open reset **without Settings underneath**.

A second DialogHost bug can hide Move progress: **New downloads** (non-modal) is replaced by the onboarding/progress dialog; a deferred `on_dismiss` from the first dialog closes the second. A second Move click then hits `if self.library_move_running: return []` and appears to “stop immediately.”

---

## 2. Evidence table

| Item | Value | Source |
|------|--------|--------|
| `library_root` | `K:\JEREMY'S FILES\video` (**bare folder**, not `FrameForge\Library`) | `settings.library_root` |
| `library_onboarded` | `1` | `settings.library_onboarded` |
| `library_items` | **0 rows** | SQLite count |
| Completed jobs | 69 | `jobs.status` |
| Jobs with `download_path` rewritten to missing `K:\…\Uncategorized\…` | **58** | path prefix `K:` + `Path.is_file()==False` |
| Jobs still eligible (`job_media_file` finds a real video) | **11** | matches log `batch jobs=11` |
| Videos still in `Downloads\FrameForge\youtube\` | **75** | disk `iterdir` |
| `Uncategorized` videos | **0** | `K:\JEREMY'S FILES\video\Uncategorized` is empty |
| Site leftovers after Repair | youtube: 0 `.part` / 0 `.aria2` / 0 `.info.json`; `temp\junk` 22; `metadata` 92 | disk |
| Field move log (only non-pytest / non-probe) | `library_move_20260816_102055.log` **84 bytes, 2 lines, no OK** | see excerpt |
| Probe (tiny files, not this tree) | `library_move_20260816_100450.log` moved=3 | `docs/FIELD_MIGRATE_v0.6.3.md` |

### 2.1 The one file that always “moves”

| Field | Value |
|--------|--------|
| **job_id** | **2** (also queued again as jobs **3** and **23** — same path) |
| **title** | Agentic AI – Complete Course for Beginners |
| **src (exists)** | `C:\Users\jroba\Downloads\FrameForge\youtube\Agentic AI – Complete Course for Beginners [Zy7EXDONlTY].mp4` |
| **size** | **4,481,858,171 bytes** (~4.17 GiB) |
| **job 1 path (missing)** | `K:\JEREMY'S FILES\video\Uncategorized\Agentic AI – Complete Course for Beginners [Zy7EXDONlTY].mp4` |

Job 1 is the **previous** attempt’s rewritten dest: path points at Uncategorized, file is gone, `job_media_file` returns `None`, so it is **not** in the 11-job list. Jobs 2/3/23 still point at the C: original. Stable sort always starts with job 2.

### 2.2 UI list vs worker

`confirm_library_move` (`app.py:1377–1408`) builds `pending_jobs` + `pending_disk` then `mover.start([j.id for j in pending_jobs], extra_paths=pending_disk)`.

Live reconstruction (same functions the UI uses):

- **UI jobs:** 11  
- **UI disk:** 70 (youtube/samplelib videos whose **job rows** already point at missing K: paths, so they are not in the 11)  
- **Worker `work` length:** 81  
- Log: `batch jobs=11 disk=70` — **the worker received the full list**, not a 1-item filter.

### 2.3 Field log excerpt (this machine’s youtube tree)

`C:\Users\jroba\Downloads\FrameForge\temp\library_move_20260816_102055.log` (mtime 2026-08-16 10:20:55, **entire file**):

```
start library_root=K:\JEREMY'S FILES\video purged_missing=0
batch jobs=11 disk=70
```

Interpretation (`mover.py:200–227`): `OK` is written **after** `transfer_file` returns; `FAIL`/`ABORT` only on exceptions. **No line after `batch` ⇒ not an exception on file 2, not `batch size 1`.** The process left the loop during file 1 (blocked in `copy2`, or killed by quit before `OK`).

All other `library_move_*.log` files from today are **pytest tmp** or the **3-file K: probe**, not this tree.

### 2.4 Code anchors

| Behavior | Location |
|----------|----------|
| Batch log then per-file `OK` only after transfer | `src/frameforge/library/mover.py:126–210` |
| Cancel checked **between** files, not during copy | `mover.py:166–190` |
| Cross-drive `copy2` + size verify + unlink, **no progress callback** | `src/frameforge/library/transfer.py:29–66` |
| Eligibility = existing video on `download_path`/`output_path` | `src/frameforge/library/ingest.py:25–31, 68–82` |
| Job order | `src/frameforge/db/repository.py:199–204` (`ORDER BY priority DESC, id ASC`) |
| Move from “N new downloads” opens onboarding with `replace=True` | `src/frameforge/ui_flet/app.py:1391, 1238, 1427–1438` |
| Second Move click no-ops if worker still running | `app.py:1372–1373` |
| Quit cancels + joins **2.5s** then destroys process | `app.py:57, 2413–2436` |
| Reset opens on top of Settings (single-dialog host) | `app.py:2232–2234`; `dialog_host.py:57–88` |
| Settings `on_dismiss` → `close_dialog` | `settings_dialog.py:172–174, 294` |
| `wire_closable` forces `modal=False` on reset | `dialog_host.py:72–75`; `modals.py:23–36` |
| Reset SQL does **not** revert `jobs.download_path` | `src/frameforge/library/reset.py:8–22` |
| Post-move `heal_library_paths` still `rglob`s entire `library_root` | `scan.py:64–72, 104–106` |
| `mark_onboarded` on Skip even if files remain | `app.py:1478–1484` |

---

## 3. Sequence of one failed Move click

User path: Library tab (already onboarded) → “N new downloads — Move to Library?” → **Move to Library**.

```mermaid
sequenceDiagram
    participant U as User
    participant ND as library_new dialog
    participant DH as DialogHost
    participant UI as confirm_library_move
    participant W as LibraryMoveRunner thread
    participant FS as copy2 C: to K:

    U->>ND: Move to Library
    ND->>UI: on_yes
    UI->>UI: purge_missing (0 rows; still rglob K: video tree)
    UI->>UI: pending = 11 jobs + 70 disk
    UI->>UI: progress 0/81 Starting…
    UI->>DH: open library_onboard replace=True
    DH->>DH: close() pops library_new
    Note over DH,ND: library_new on_dismiss=close_dialog may run after onboard is shown and pop the progress dialog
    UI->>W: start(job_ids=11, extra_paths=70)
    W->>W: log start + batch jobs=11 disk=70
    W->>UI: on_progress 1/81 Agentic AI… (job 2)
    W->>FS: transfer_file copy2 4.48 GiB (no ticks, cancel ignored)
    alt User sees empty UI / clicks Move again
        U->>UI: confirm_library_move
        UI-->>U: return [] because library_move_running
    else User closes window
        UI->>W: cancel (only observed between files)
        UI->>UI: join 2.5s then hard_exit
        FS--xW: process killed; no OK line; Uncategorized still empty
    end
```

**What does not happen:** empty remaining list, exception on file 2, `batch size 1`, or stale `library_items` blocking job 2.

**Why it looks like “only one file moved”:** the bar shows job 2’s title and never advances (copy has no intra-file ticks). A prior attempt already rewrote **58 other job paths** to Uncategorized without leaving files there, so those titles never appear in the job prefix of the batch. Disk extras (70) are **after** the 11 jobs, so they never start.

---

## 4. Why v0.6.2 / v0.6.3 did not fix this machine

| Prior claim | This machine |
|-------------|--------------|
| Progress / `between_files` outside `try` aborts the batch | Log has **no** `FAIL`/`ABORT`. Callbacks are inside `try` (`mover.py:156–162, 182–186`). |
| Stale `library_items` + `job_id` block re-move | **`library_items` count = 0.** `purged_missing=0`. |
| Tiny 3-file cross-drive Move proves field migrate | Probe used **new** jobs and **~KB files** on `K:\FrameForgeProbe063\…`. This tree’s first file is **4.48 GiB** and 58 jobs have **wrong paths**. |
| Unit tests: file-2 exception still moves file 3 | Tests use **tiny clips** and never call `copy2` on a multi-GB file; they never open **library_new → library_onboard** on a real Flet page. |

**Dominant bug for this youtube tree:** first work item is a multi-gigabyte cross-drive copy with no heartbeat; quit/dialog teardown kills it; sort order retries the same job.

**Amplifiers (still real, not the 1-item filter):**

1. **58 job rows already rewritten** to missing Uncategorized paths; `completed_jobs_not_in_library` skips them (`ingest.py:76–78`). Files still sit in `youtube\`. Reset does not restore `jobs.download_path`.
2. **Duplicate job rows** (Agentic AI ×3, System Design ×3) make the first three *job* slots the same 4.48 GiB file.
3. **`library_root` is the bare `K:\JEREMY'S FILES\video` tree.** Every `videos_by_filename(store.root())` walks the user’s whole video library, not `FrameForge\Library`. `scan_ingest_folder` still calls `heal_library_paths` first (`scan.py:106`).
4. **`library_onboarded=1` with 0 indexed files** — Skip (`app.py:1484`) or a reset that never completed in the GUI, then folder re-pick / skip.

---

## 5. Reset Library onboarding dialog

**Handler:** Settings → `on_reset_library=self.open_reset_library` (`app.py:2225`) → `confirm_reset_library_dialog` (`library.py:526–541`, constructed `modal=True`) → `dialogs.open("reset_library", dlg)` (`app.py:2232–2234`).

**Why it disappears before a choice:**

1. `DialogHost` keeps **one** dialog (`dialog_host.py:16–17, 69–70`). Opening reset **closes Settings first**.
2. Settings is `modal=False` with `on_dismiss=cancel` → `close_dialog()` (`settings_dialog.py:172–174, 285–294`).
3. Flet `pop_dialog()` delivers that `on_dismiss` **after** `open()` has set `current` to the reset dialog → **`close_dialog()` closes reset**.
4. Independently, `kind not in {quit, library_onboard}` applies `wire_closable` (`dialog_host.py:72–75`), which **sets `modal=False`** and `on_dismiss=self.close`. Barrier click / mouse-up from the Settings button can dismiss reset immediately.

**If Reset were clicked:** `reset_library_state` (`reset.py:8–22`) **does** `DELETE` library tables, `library_onboarded=0`, `library_root=''`, re-seeds collections. It does **not** rewrite `jobs.download_path` / `output_path`. After a successful reset, the 58 K: paths would **still** be missing; those files would only return via the disk scanner, still **behind** job 2’s 4.48 GiB copy.

`test_ui_reset_library_reopens_onboarding` (`tests/test_library_reset.py:35–47`) calls `open_reset_library()` with **no Settings dialog open** and a FakePage — it cannot see this failure.

---

## 6. Related systems (brief)

### Repair folders

v0.6.3 UX (busy text + summary dialog) is in `app.py` / `settings_dialog.py`. **Field disk matches a successful repair:** `youtube\` has **0** `.part` / `.aria2` / `.info.json`; `temp\junk` = 22; `metadata` = 92. Remaining clutter in site folders is **finished mp4s** (75 youtube + 2 samplelib), which Repair is not supposed to move.

Startup repair still uses `toast=False` (`app.py:2479`).

### Download `-P temp` / home

`YtDlpDownloader._yt_paths` (`ytdlp.py:260–262`): `home` = site folder, `temp` = `temp\dl` when under FrameForge root. Leftover parts in site folders on this machine are **already triaged**. New downloads were not re-run in this audit.

### Quit / `prevent_close`

`attach_page` sets `prevent_close=True` (`app.py:2471`). `_commit_quit` always `cancel_library_move()` then `wait_library_move(2.5)` (`app.py:57, 2428–2436`). **Cancel does not abort `copy2`.** A 4.48 GiB copy is killed mid-file. Incomplete dest would normally remain; Uncategorized is currently **empty** (copy never created a durable dest, or it was removed).

### SQLite integrity

| Flag | State |
|------|--------|
| onboarded + empty index | **Yes** (`onboarded=1`, `library_items=0`) |
| Missing-path job rows | **58** (not `library_items` — **jobs** paths) |
| Duplicate `download_path` | Agentic AI ×3, System Design ×3 |

### Other `mark_onboarded` / cancel paths

- Skip onboarding: `app.py:1484` (cancels move if running, else marks onboarded **with files still in youtube**).
- `confirm_library_move` with empty pending: `app.py:1379–1381`.
- `_on_library_move_done` when finishing and nothing remaining: `app.py:1341–1342`.
- `_on_library_move_done` **always** `open_library_onboarding()` even when already onboarded (`app.py:1356`) — wrong dialog after a field Move, not the 1-file stop.

---

## 7. Test suite honesty

Suite **469 passed** does not exercise this failure mode.

| Test | What it proves | Gap vs field |
|------|----------------|--------------|
| `test_run_library_move_file2_error_still_moves_file3` | Exception on file 2 does not drop file 3 | Field has **no** file-2 exception; file 1 never returns |
| `test_run_library_move_progress_callback_error_does_not_abort` | UI callback exceptions | Not the field stop |
| `test_library_move_skips_part_files_and_purges_stale_rows` | Missing **library_items** | Field has **0** library_items; **jobs** paths are stale |
| `test_library_move_runner_cancel_mid_batch` | Cancel **between** files after 1 tiny move | Cancel cannot stop `copy2`; quit uses 2.5s join |
| `test_confirm_library_move_does_not_block_ui_thread` | FakePage + 4 tiny files + hook sleep | FakePage: `_migrate_disk_roots` returns `[]` (`app.py:1089–1090`); **no DialogHost replace**; **no GB copy** |
| `test_ui_move_keeps_summary_not_toast_only` | Summary string on FakePage | Never `library_new` → `library_onboard` |
| `test_migrate_includes_disk_files_without_jobs` | extra_paths on tiny files | Does not put 70 disk files **after** a 4.48 GiB first job |
| 3-file probe / `FIELD_MIGRATE_v0.6.3.md` | Tiny cross-drive copy works | Different root, different jobs, KB files |
| `test_ui_reset_library_reopens_onboarding` | Reset API + FakePage | **Settings not open**; no `on_dismiss` cascade |

**Insufficient / mock-away:** FakePage skips live Flet dismiss; tests never stack Settings→reset; no test with rewritten `jobs.download_path` + file still in `youtube\`; no test that `copy2` of a large file holds the bar at 1/N; no test that a second `confirm_library_move` is a no-op while running.

---

## 8. Recommended fix plan (proposals only — do not implement here)

1. **Heartbeat + cancellable transfer.** During cross-drive copy, log `COPY #n src=… bytes=…/…` on a timer; honor `cancel` (and quit) **inside** the copy (chunked copy or `shutil.copyfileobj` loop). Do not rely on `copy2` as an uninterruptible 4 GiB syscall.
2. **Do not sort a 4 GiB file first without saying so.** Show size in the Move dialog (“Copying 4.2 GB to K:… this can take many minutes”). Optionally process smallest-first or cap concurrent copy with visible ETA. Duplicate `download_path` rows: move once, then index/skip clones.
3. **Heal job paths, not only `library_items`.** If `download_path` is under library_root but missing, and the same `*[id].mp4` still exists under the download root, restore the job path (or treat as disk orphan **before** other jobs). Reset must offer “revert job media paths that point at missing Uncategorized files.”
4. **DialogHost stacking.** Nested confirms (reset from Settings, progress from New downloads) must not `close()` the parent in a way that replays `on_dismiss` onto the child. Keep Settings open and show reset as a child, **or** ignore `on_dismiss` from the dialog being replaced, **or** exclude `reset_library` from `wire_closable` and keep it `modal=True`. Same for `library_new` → `library_onboard`.
5. **Quit vs in-flight copy.** Join timeout must be “until cancel observed **or** user-confirmed abort of copy,” not 2.5s hard kill of a 4 GiB `copy2`. Leave a partial dest in `temp\` not Uncategorized, and log `ABORT in-copy`.
6. **`library_root` contract.** If stored root is a bare folder (not `…\FrameForge\Library`), warn and offer to retarget; stop `rglob` of the entire `K:\JEREMY'S FILES\video` tree on every Move/heal.
7. **Tests that would have caught this:** (a) Settings open → `open_reset_library` → dialog still `kind==reset_library` after a simulated `on_dismiss` from Settings; (b) `library_new` replace with onboard → progress dialog still current; (c) fixture: 58 jobs with missing K: paths + files still in a fake youtube dir + one  existing C: path → first copy is that file and disk extras are not dropped; (d) transfer hook that blocks 10s: quit must not need the copy to finish, and log must show in-copy abort; (e) duplicate job_ids sharing one path → one transfer.
8. **Do not claim migrate fixed** until a field log from **this** `library_root` shows `OK #2` (and preferably `OK` through the 11 jobs) with dest files in Uncategorized.

---

## 9. What we did not change

- No edits under `src/`, `tests/`, `pyproject.toml`, or version files.
- No schema or SQLite writes (DB opened `mode=ro`).
- No moves, deletes, Recycle, or copies of user media on `C:\Users\jroba\Downloads\FrameForge\` or `K:\JEREMY'S FILES\video`.
- No re-run of Library Move, Repair, or Reset.
- This file is documentation only.

---

## 10. Direct answers (acceptance)

| Question | Answer |
|----------|--------|
| Exact identity of the one file | Job **2**, 4,481,858,171 bytes, `…\youtube\Agentic AI – Complete Course for Beginners [Zy7EXDONlTY].mp4` |
| UI list vs worker | **11 + 70 = 81** both sides; log confirms |
| Why stop after file 1 | **Blocked/killed inside `copy2` of file 1**, not empty list / file-2 exception / batch size 1 |
| Log shape | **`OK #1` never written**; starts with **batch size 81** |
| Why always the same file | Stable `id ASC` + job 2 still on C: because copy never completes; jobs 3 & 23 are the same path |
| Reset auto-dismiss | Settings `on_dismiss` + single-dialog `replace` + `wire_closable` non-modal |
| Does reset clear flags when it “succeeds”? | **Yes, if `confirm_reset_library` runs.** Field symptom is it **does not run**. Even then, **job paths stay wrong.** |

---

## 11. Follow-up (v0.6.7 code — field gate still open)

Shipped in package **0.6.7**:

- Cross-drive copy is chunked (`copyfileobj`-style loop), logs `COPY #n bytes=a/b`, honors cancel **during** copy. Dest-side `.ffpartial` is removed on abort; source is kept. No `shutil.copy2` in `library/transfer.py`.
- Work list is **deduped** by resolved source path (jobs 2/3/23 → one transfer) and **smallest-first**.
- Missing Uncategorized/library `download_path` values are healed from the download tree (`*[id].mp4`) before Move. Reset can revert those job paths (does not delete media).
- DialogHost: Settings `on_dismiss` cannot close `reset_library`; `library_new` dismiss cannot close `library_onboard`. Reset stays modal until the user chooses.
- Quit join wait is 15s after cancel so a chunk can finish; cancel is cooperative.

**Field gate:** this machine’s youtube tree is **not claimed fixed** until a new `temp\library_move_*.log` from **that** tree contains `OK` for a second file (`OK #2+`). Pytest and the 3-file probe still do not count. See [LIBRARY.md](LIBRARY.md).
