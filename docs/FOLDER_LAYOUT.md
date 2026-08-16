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
| `database/frameforge.db` | SQLite WAL database (`-wal` / `-shm` sit beside it) |
| `cookies/`, `archive/` | Auth cookies and download archive |
| `temp/`, `models/` | Working files and ONNX models |

On init, `ensure_output_tree()` creates these subfolders and **repairs** a chaotic root:

- Loose `*.jpg` / `*.jpeg` / `*.png` / `*.webp` at the FrameForge root → `thumbnails/`
- Loose `frameforge.db` plus `-wal`/`-shm` → `database/`
- Loose video files at the FrameForge root → `videos/`

Existing files already in the right subfolder are left alone. Repair never deletes.

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
