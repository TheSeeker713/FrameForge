# Library

Local media catalog. **No cloud, no accounts, no telemetry sync.** Metadata lives in the same SQLite file as the download queue (`frameforge.db`). Files live under a folder you choose (any drive).

Queue and History are unchanged: completed downloads stay playable from the Queue thumbnail/row even after they are moved into Library.

The **Library** tab replaced **Thumbnails**. Preview images still cache under `%USERPROFILE%\Downloads\FrameForge\thumbnails\` for Queue cards.

## Onboarding

1. First open of Library: pick a library root folder.
2. FrameForge scans **completed** jobs that still have a file on disk.
3. Confirm to **move** those files into `library_root/Uncategorized/` (filename kept; job `download_path` / `output_path` updated only after the destination exists).
4. Later opens: if new completed downloads are not in the index, a modal offers “N new downloads — Move to Library?” **Yes** / **Not now**.

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

Migration 4: `library_items`, `library_collections`, `library_item_collections`, `library_watch_folders`. Settings keys: `library_root`, `library_onboarded`.
