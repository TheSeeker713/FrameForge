# Changelog

## 0.5.0

- Full GUI rewrite on Flet (light SaaS chrome; CustomTkinter is not the default window)
- Floating selection bar; contextual Upscale / Convert
- Fail-pause on retry and hard unknown; stderr tail on yt-dlp exits
- Settings single-instance; display version 0.5.0

## 0.4.0

- Pause / resume downloads (hard-stop, keep partials, yt-dlp continue)
- Quit while busy: cancel, pause, or wait-for-current (exactly three options)
- Optional close-to-system-tray (default off); tray Show / Pause-Resume / Quit
- Import cookies from browser (Firefox first; Chromium fallback; manual Netscape still available)

## 0.3.0

- Original 11 items **100% PASS** (live subprocess speed/ETA; failure-driven auth hints)
- Structured error categories + richer error panel
- History tab (SQLite terminal jobs; soft-hide)
- Thumbnails cache + Queue/History previews + Thumbnails tab
- Worker loop survives handler exceptions; ORT dual-thread test race fixed

## 0.1.0

- Phase 0–5 initial release scaffold and application
- Sequential SQLite WAL queue
- yt-dlp + aria2c downloads
- TXT/MD bulk import
- ONNX upscale pipeline with stop/resume and audio preservation
- CustomTkinter dark GUI
- PyInstaller portable build
