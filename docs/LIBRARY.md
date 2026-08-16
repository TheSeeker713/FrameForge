# Library

Local media catalog. **No cloud, no accounts, no telemetry sync.** Metadata lives in the same SQLite file as the download queue (`frameforge.db`). Files live under a folder you choose (any drive).

Queue and History are unchanged: completed downloads stay playable from the Queue thumbnail/row even after they are moved into Library.

The **Library** tab replaced **Thumbnails**. Preview images still cache under `%USERPROFILE%\Downloads\FrameForge\thumbnails\` for Queue cards.

## Onboarding

Onboarding is two steps. **`library_root` and `library_onboarded` are separate.** Choosing a folder does **not** finish setup.

1. First Library open if `library_onboarded` is not set → step A: pick a library root (any drive). Only `library_root` is saved.
2. Step B (same session, wizard stays open / resumes here if you reopen Library): scan completed jobs that still have a file on disk and are not in `library_items`. Show the count plus a short sample list.
   - **Move to Library** — files move on a **background worker thread** (never the Flet UI thread). Destination is `library_root/Uncategorized/` (filename kept; job paths update only after the destination exists). The wizard shows a determinate progress bar, “Moving N of M…”, the current filename, and **Cancel**. Per-file errors are logged and counted; the rest of the batch continues. On a clean finish with nothing left to move, set `library_onboarded`. Cancel stops before the next file; already-moved files stay in Library (no rollback).
   - **Skip for now** — keep `library_root`, set `library_onboarded`, leave files in the download folders. Import later from the empty-state **Import completed downloads** button.
3. If a move fails or is cancelled with files still outside Library, `library_onboarded` stays false and the transfer step stays up with a moved/failed/skipped summary so you can retry or skip.
4. **Quit during a move:** X / Quit signals cancel, waits up to ~2.5s for the worker, then continues normal shutdown. `prevent_close` is released immediately so the window is never stuck behind a freeze.
5. Later opens (already onboarded): if new completed downloads are not in the index, a modal offers “N new downloads — Move to Library?” **Yes** / **Not now**.

Re-opening Library with a root but `library_onboarded=false` resumes at step B.

## Layout

- Grid: thumb, title, source, resolution, date
- Play (default player), Reveal in Explorer (`explorer /select,path` only — no shell theme changes), Upscale when height is known and **&lt; 2160**
- Empty state with a setup / move CTA

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
