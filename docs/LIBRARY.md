# Library

Local media catalog. **No cloud, no accounts, no telemetry sync.** Metadata lives in the same SQLite file as the download queue (`database/frameforge.db` under the download FrameForge root). Library **files** live under `<picked>/FrameForge/Library/` — see [FOLDER_LAYOUT.md](FOLDER_LAYOUT.md).

Queue and History are unchanged: completed downloads stay playable from the Queue thumbnail/row even after they are moved into Library.

The **Library** tab replaced **Thumbnails**. Preview images still cache under `%USERPROFILE%\Downloads\FrameForge\thumbnails\` for Queue cards.

## Onboarding

Onboarding is two steps. **`library_root` and `library_onboarded` are separate.** Choosing a folder does **not** finish setup.

1. First Library open if `library_onboarded` is not set → step A: pick a library root (any drive). FrameForge creates `<picked>/FrameForge/Library/` and stores that as `library_root` (never the bare picked folder).
2. Step B (same session, wizard stays open / resumes here if you reopen Library): scan **completed jobs with a file on disk** and **video files under the download tree** (`Downloads/FrameForge/…`) that are not in `library_items`. Show the combined count plus a short sample list.
   - **Move to Library** — files move on a **background worker thread** (never the Flet UI thread). Destination is `library_root/Uncategorized/` (filenames kept; job paths update only after the destination exists). Same-drive uses rename; **cross-drive** is a **chunked copy** (cancel is checked every chunk) → size verify → unlink source. Large files log `COPY #n bytes=a/b` and the UI can show percent / “4.2 GB”. Duplicate job rows that share one source path are moved **once**. Before the batch, jobs whose `download_path` points at a **missing** Uncategorized/library file are healed to the matching `*[id].mp4` under the download tree (youtube/…) when that file still exists. Only finished videos (not `.part` / `.aria2` / json). Stale `library_items` whose path is missing are dropped (after heal) so the same job can move again. The wizard shows a determinate progress bar, “Moving N of M…”, the current filename, and **Cancel**. Cancel during a copy does **not** write a finished dest (dest-side `.ffpartial` is removed; source stays). The bar stays up until a **summary** (moved / failed / skipped / disk files, plus log path). Every file is appended to `Downloads\FrameForge\temp\library_move_<timestamp>.log` (src, dst, ok/fail, `ABORT in-copy`, traceback). Per-file errors **and** progress-callback errors are logged and counted; the rest of the batch continues. After the batch, Uncategorized is scanned for orphans (not the entire drive). On a clean finish with nothing left to move, set `library_onboarded`. Already-moved files stay in Library (no rollback).
   - **Skip for now** — keep `library_root`, set `library_onboarded`, leave files in the download folders. Import later from the empty-state **Import completed downloads** button.
3. If a move fails or is cancelled with files still outside Library, `library_onboarded` stays false and the transfer step stays up with the summary so you can retry or skip. Success also keeps the summary until you click **Done** (not toast-only).
4. **Quit during a move:** X / Quit signals cancel (chunked copy aborts at the next chunk), waits up to ~15s for the worker, then continues normal shutdown. `prevent_close` is released immediately so the window is never stuck behind a freeze.
5. Later opens (already onboarded): if new completed downloads are not in the index, a modal offers “N new downloads — Move to Library?” **Yes** / **Not now**.

Re-opening Library with a root but `library_onboarded=false` resumes at step B.

**Reset (dev / retest):** Settings → Advanced → **Reset Library onboarding**, or `.\scripts\reset_library.ps1` / `.\scripts\reset_library_state.ps1` / `python -m frameforge --reset-library`. Clears the index, collections, watch folders, `library_root`, and `library_onboarded`. **Does not delete media files.** Completed jobs that still point at **missing Uncategorized** paths are restored to the matching file under the download folders when one exists. After reset, onboarding is pick folder → `<pick>/FrameForge/Library/Uncategorized` → scan **all** download-tree videos (every site folder) → Move with progress → summary → playable grid. The reset confirm stays until you choose Reset or Cancel (Settings dismiss must not close it).

### Field gate (v0.6.7)

The 2026-08-16 audit of this machine’s youtube tree (`library_move_20260816_102055.log`, stuck in a 4.48 GB `copy2` of job 2) is **not claimed fixed** until a **new** log from that same tree shows `OK` for file 2 or later (`OK #2+`). Tiny pytest files and the 3-file K: probe do not count. See [AUDIT_FULL_v0.6.3_FIELD.md](AUDIT_FULL_v0.6.3_FIELD.md).

## Layout

- Grid: one card per **playable** indexed file (title, thumb if the thumb file exists, resolution). Count in the toolbar equals visible cards.
- Missing `library_items.path` is re-found under `library_root` by filename before the grid loads.
- Click thumb or card → Play via the Windows default player (`os.startfile`). Reveal uses `explorer /select,path` only (no shell theme changes). Upscale when height is known and **&lt; 2160**.
- If videos exist on disk under the library folder but are not indexed, **Scan library folder** imports those orphans.
- Empty state with a setup / import / scan CTA. GridView is given a bounded host and builds tiles immediately (not on-demand), so a populated library is never a blank gray panel.

**Duplicates:** toolbar **Duplicates…** groups files by normalized title (bracket `[id]` segments ignored) + file size + duration (ffprobe, cached on the row). Keep higher resolution / newer mtime; extras go to Recycle Bin.

**Junk:** toolbar **Junk files…** lists `.part` / `.ytdl` / `.temp` / zero-byte / orphan sidecars. **Delete** uses Recycle Bin only; **Keep** leaves them; **Move…** relocates to a folder you pick.

## Collections (primary folder + extra tags)

Seeded **Types** (folders): Music Videos, Tutorials, Documentaries, Shorts & Clips, Movies, Series, Live & Streams, Podcasts & Talk, Uncategorized.

Seeded **Subjects** (tags, multi-assign): Comedy, Horror, Sci-Fi, Action, Drama, Animation & Cartoons, Gaming, Tech, Education, News, Sports, Fitness, Food & Cooking, Travel, DIY & Crafts, ASMR, Nature, Art & Design, Fashion, Finance, Other.

Seeded **Sources** (filters, auto from extractor/host): YouTube, TikTok, X (Twitter), Reddit, Facebook, Instagram, Vimeo, Twitch, Other.

**One primary folder path, many tags.** Adding a Type or custom collection **moves** the file to `library_root/<CollectionName>/` and updates SQLite paths. Extra collections are tags only.

Custom names are allowed (brand-specific, personal, etc.).

## System flags (chips, not folders)

Favorites, Watch Later, Recently Added (7 days), Upscale candidate (≤720p), 1080p, 4K+ (upscale blocked).

## Extra folders

Settings can add watch folders: **index** (catalog in place) or **import** (same move policy as completed downloads). Changing the library root does not auto-move existing files; re-index after you confirm.

## Private

See [LIBRARY_PRIVATE.md](LIBRARY_PRIVATE.md). Copies into a password zip; originals stay until you Keep / Recycle Bin / Move.

## Schema

Migration 4: `library_items`, `library_collections`, `library_item_collections`, `library_watch_folders`. Settings keys: `library_root` (folder pick), `library_onboarded` (set only after Move succeeds or Skip).
