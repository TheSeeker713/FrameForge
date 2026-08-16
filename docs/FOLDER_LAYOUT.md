# Folder layout

FrameForge never dumps media, thumbnails, or SQLite files into a bare picked folder.

## Download root

`%USERPROFILE%\Downloads\FrameForge\` (created on launch):

| Path | Role |
|------|------|
| `videos/` | Loose videos found at the FrameForge root (repair) |
| `youtube/`, `x.com/`, … | Per-site downloads |
| `downloads/` | Legacy download folder |
| `upscaled/`, `converted/` | Post-process output (per-site children) |
| `thumbnails/` | Queue/Library preview images |
| `metadata/` | yt-dlp `.info.json` after a successful download (and repair leftovers) |
| `database/frameforge.db` | SQLite WAL database (`-wal` / `-shm` sit beside it) |
| `cookies/`, `archive/` | Auth cookies and download archive |
| `temp/` | Working files; `temp/dl/` yt-dlp/aria2 **in-flight** parts; `temp/junk/` leftover `.part` / `.aria2` / `.ytdl` (not Recycled); `temp/<job>/frames/` PNG extract (deleted after successful upscale; orphan sweep on Repair) |
| `temp/library_move_*.log` | Per-file Library migrate log |
| `models/` | ONNX models |

On init, `ensure_output_tree()` creates these subfolders and **repairs loose files at the FrameForge root only** (fast, so CLI and import stay snappy):

- Loose `*.jpg` / `*.jpeg` / `*.png` / `*.webp` at the FrameForge root → `thumbnails/`
- Loose `frameforge.db` plus `-wal`/`-shm` / leftover `frameforge.db.*` → `database/` (never overwrites a live `database/frameforge.db`)
- Loose video files at the FrameForge root → `videos/`

**Per-site folders stay as media homes** (`youtube/`, `x.com/`, `samplelib.com/`, `videos/`, `downloads/`, …). Videos are not relocated out of those folders.

On GUI attach (background thread, does not freeze startup) and via **Settings → Repair folders** (button shows **Repairing folders…**, then a **summary dialog** with counts):

- Image thumbs sitting **next to videos** in every site/media folder → `thumbnails/` (name collision: `name (2).ext`)
- `jobs.options_json.thumbnail_path` and `library_items.thumb_path` are updated when those files move
- Leftover `.part` / `*.part.aria2` / `.ytdl` / zero-byte videos → `temp/junk/` (not Recycled; Junk UI can still Recycle later)
- Leftover `.info.json` in site folders → `metadata/`

**New downloads:** yt-dlp `paths.temp` is `temp/dl/`; `paths.home` is the per-site folder. Finished media lands in `youtube/` etc. `.info.json` is moved to `metadata/` after success. Library ingest ignores non-video files.

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

Queue and History keep using `Downloads\FrameForge\database\frameforge.db`. Library metadata lives in that same database; library **media** lives under the picked `FrameForge/Library/` tree.
