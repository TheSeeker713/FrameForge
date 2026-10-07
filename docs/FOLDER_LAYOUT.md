# Folder layout

FrameForge never dumps media, thumbnails, or SQLite files into a bare picked folder.

## Download root

When `K:\JEREMY'S FILES` exists, the whole app root is `K:\JEREMY'S FILES\FrameForge\` (downloads, database, cookies, models, and temp). The profile `Downloads\FrameForge` folder is not used. `FRAMEFORGE_ROOT` overrides that root. Pytest redirects `USERPROFILE` and stays on the temp tree.

`<FrameForge root>\` (created on launch):

| Path | Role |
|------|------|
| `downloads/<bucket>/<category>/` | All new video downloads |
| `downloads/porn/<category>/` | Adult / pornographic hosts |
| `downloads/youtube/<category>/` | YouTube (and aliases) |
| `downloads/upscaled/`, `downloads/converted/` | Post-process output |
| `downloads/videos/` | Loose videos found at the FrameForge root (repair) |
| `thumbnails/` | Queue/Library preview images |
| `metadata/` | yt-dlp `.info.json` after a successful download (and repair leftovers) |
| `database/frameforge.db` | SQLite WAL database (`-wal` / `-shm` sit beside it) |
| `cookies/`, `archive/` | Auth cookies and download archive |
| `temp/` | Working files; `temp/dl/` yt-dlp/aria2 **in-flight** parts; `temp/junk/` leftover `.part` / `.aria2` / `.ytdl` (not Recycled); `temp/<job>/frames/` PNG extract |
| `temp/library_move_*.log` | Per-file Library migrate log |
| `models/` | ONNX models |

Site folders are **never** created as siblings of `database/` / `models/`. They live only under `downloads/`.

On init, `ensure_output_tree()` creates these subfolders, relocates leftover root site folders into `downloads/`, and **repairs loose files at the FrameForge root only** (fast, so CLI and import stay snappy):

- Loose `*.jpg` / `*.jpeg` / `*.png` / `*.webp` at the FrameForge root → `thumbnails/`
- Loose `frameforge.db` plus `-wal`/`-shm` / leftover `frameforge.db.*` → `database/` (never overwrites a live `database/frameforge.db`)
- Loose video files at the FrameForge root → `downloads/videos/`

**Per-bucket folders under `downloads/` stay as media homes.** Videos are not relocated out of those folders during normal use.

On GUI attach (background thread) and via **Settings → Repair folders**:

- Image thumbs sitting **next to videos** in download trees → `thumbnails/`
- `jobs.options_json.thumbnail_path` and `library_items.thumb_path` are updated when those files move
- Leftover `.part` / `*.part.aria2` / `.ytdl` / zero-byte videos → `temp/junk/`
- Leftover `.info.json` in media folders → `metadata/`

**New downloads:** yt-dlp `paths.temp` is `temp/dl/`; `paths.home` is `downloads/<bucket>/<category>/`. Finished media lands there. `.info.json` is moved to `metadata/` after success. Library ingest ignores non-video files.

Repair never Recycles. Existing files already in the right subfolder are left alone.

## Library pick

Choosing a library folder creates:

```
<picked>/FrameForge/Library/Uncategorized
<picked>/FrameForge/thumbnails
<picked>/FrameForge/database
```

`library_root` in SQLite is **`<picked>/FrameForge/Library`**, never the bare picked folder.

If you pick a folder that is already named `FrameForge`, Library is `<picked>/Library`. If you pick `…/FrameForge/Library`, that path is used as-is (no extra nesting).

The same loose-file repair runs under the library `FrameForge` folder.

Queue and History keep using `database\frameforge.db` under the app root. Library metadata lives in that same database; library **media** lives under the picked `FrameForge/Library/` tree (or is indexed in place from `downloads/`).
