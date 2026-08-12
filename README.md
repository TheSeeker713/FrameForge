# FrameForge

Fully local Windows video downloader + AI video upscaler.

**Stack:** Pure Python · CustomTkinter · yt-dlp · FFmpeg · aria2c · ONNX (DirectML preferred)

**Hardware target:** Windows 11 Pro, AMD Ryzen 7 6800H + Radeon 680M, 32 GB RAM

## Why FrameForge

Most open-source yt-dlp GUIs focus on concurrent downloads and skip local AI upscaling. Upscalers are usually separate tools. FrameForge differentiates by:

- Pure Python + CustomTkinter
- **Strictly sequential** single-job downloads
- **SQLite WAL** persistent queue (survives restarts)
- **TXT/MD bulk import** with preview, confirmation, and dedupe
- Integrated local ONNX upscaling (DirectML preferred, CPU fallback)
- AMD-friendly, offline-after-setup design
- All user media under `%USERPROFILE%\Downloads\FrameForge\`

## Features

- Highest practical quality downloads via yt-dlp + aria2c + FFmpeg merge
- Persistent job queue with priority, cancel, retry
- Optional upscale-after-download stage (still sequential)
- Dark minimal GUI: paste URL, bulk import, live queue, **History** and **Thumbnails** tabs, settings
- Live download **% / speed / ETA** on the killable yt-dlp subprocess path
- **Pause / Resume** downloads (hard-stop, keep `.part` files, continue on resume)
- **Quit while busy:** cancel, pause, or wait-for-current — never silent exit
- Optional **close to system tray** (default off)
- **Import cookies from browser** (Firefox first; Chromium fallback / manual Netscape)
- Failure-driven **Authenticate this site / Import cookies** hint (no auto-open browser loops)
- **Playlist picker:** flat expand, select a subset, enqueue pending jobs (no auto-start)
- **Per-job format** presets (Best, ≤1080p / 720p / 480p, Audio-focused)
- **Convert selected → MP3** (ffmpeg VBR `-q:a 2`, sequential worker stage)
- **Upscale resource monitor** (psutil CPU/RAM warnings; optional auto-pause)
- **Keyboard shortcuts** with Help manual (F1)

## Setup

```powershell
cd D:\_Dev\Projects\FrameForge
.\scripts\bootstrap_venv.ps1
.\.venv\Scripts\Activate.ps1
python .\scripts\create_x2_onnx.py
python -m frameforge --check-env
pytest -q
python -m frameforge --gui
```

## Portable build

```powershell
.\scripts\build_portable.ps1
# dist\FrameForge\FrameForge.exe --version
# Requires ffmpeg + aria2c on PATH; models under Downloads\FrameForge\models
```

## Output layout

`%USERPROFILE%\Downloads\FrameForge\` → `downloads/`, `upscaled/`, `converted/`, `temp/`, `models/`, `archive/`, `cookies/`, `thumbnails/`, `frameforge.db`

See [docs/HISTORY.md](docs/HISTORY.md), [docs/THUMBNAILS.md](docs/THUMBNAILS.md), [docs/COOKIES.md](docs/COOKIES.md), [docs/PAUSE_RESUME.md](docs/PAUSE_RESUME.md), [docs/TRAY_AND_QUIT.md](docs/TRAY_AND_QUIT.md), [docs/PLAYLISTS.md](docs/PLAYLISTS.md), [docs/FORMATS_AND_CONVERT.md](docs/FORMATS_AND_CONVERT.md), [docs/RESOURCES.md](docs/RESOURCES.md), [docs/SHORTCUTS.md](docs/SHORTCUTS.md), [docs/V0.4_COMPLETE.md](docs/V0.4_COMPLETE.md), [docs/V0.4_PROMPT1_COMPLETE.md](docs/V0.4_PROMPT1_COMPLETE.md), and [docs/ORIGINAL11_100.md](docs/ORIGINAL11_100.md).

## License

MIT — see [LICENSE](LICENSE).
