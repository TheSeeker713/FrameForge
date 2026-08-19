# FrameForge

Fully local Windows video downloader + AI video upscaler.

**Stack:** Pure Python · Flet · yt-dlp · FFmpeg · aria2c · ONNX (DirectML preferred)

**Hardware target:** Windows 11 Pro

## Why FrameForge

Most open-source yt-dlp GUIs focus on concurrent downloads and skip local AI upscaling. Upscalers are usually separate tools. FrameForge differentiates by:

- Pure Python + **Flet** (light SaaS UI)
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
- Light **Flet** GUI (cards, floating bar, pill tabs). CustomTkinter is not the default window.
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
- **Per-site folders** for new downloads (`FrameForge\<site>\`), upscales, and MP3 converts
- **Clear selected / Clear finished** on the live queue (History keeps completed and failed work)
- **History v2:** domain filter, re-download as a new pending job, clear selected / all
- **Fail-pause:** bot/auth failures disarm the queue and show a modal with cookie / retry actions
- Optional **gentle rate mode** after bot checks (off by default); aria2c multi-connection on the fast path

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

`%USERPROFILE%\Downloads\FrameForge\` → per-site download folders (`youtube/`, `x.com/`, …), `upscaled/<site>/`, `converted/<site>/`, plus global `temp/`, `models/`, `archive/`, `cookies/`, `thumbnails/`, `frameforge.db`

See [docs/UI_REDESIGN.md](docs/UI_REDESIGN.md), [docs/ACCEPTANCE_V05.md](docs/ACCEPTANCE_V05.md), [docs/V0.5_UI_COMPLETE.md](docs/V0.5_UI_COMPLETE.md), [docs/QUEUE_CLEAR.md](docs/QUEUE_CLEAR.md), [docs/HISTORY_V2.md](docs/HISTORY_V2.md), [docs/FAIL_PAUSE.md](docs/FAIL_PAUSE.md), [docs/SPEED.md](docs/SPEED.md), [docs/HISTORY.md](docs/HISTORY.md), [docs/THUMBNAILS.md](docs/THUMBNAILS.md), [docs/COOKIES.md](docs/COOKIES.md), [docs/PAUSE_RESUME.md](docs/PAUSE_RESUME.md), [docs/TRAY_AND_QUIT.md](docs/TRAY_AND_QUIT.md), [docs/PLAYLISTS.md](docs/PLAYLISTS.md), [docs/FORMATS_AND_CONVERT.md](docs/FORMATS_AND_CONVERT.md), [docs/RESOURCES.md](docs/RESOURCES.md), [docs/SHORTCUTS.md](docs/SHORTCUTS.md), [docs/SITE_FOLDERS.md](docs/SITE_FOLDERS.md), [docs/V0.4_COMPLETE.md](docs/V0.4_COMPLETE.md), [docs/V0.4.2_COMPLETE.md](docs/V0.4.2_COMPLETE.md), [docs/V0.4_PROMPT1_COMPLETE.md](docs/V0.4_PROMPT1_COMPLETE.md), and [docs/ORIGINAL11_100.md](docs/ORIGINAL11_100.md).

## License

MIT — see [LICENSE](LICENSE).
