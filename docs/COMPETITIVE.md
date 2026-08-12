# Competitive positioning

## Landscape

| Category | Examples | Typical gap |
|----------|----------|-------------|
| yt-dlp GUIs | Stacher, Parabolic, yt-dlp-gui forks, VidBee, ArcDLP | Concurrent downloads; little/no local AI upscale |
| Upscalers | Video2X, Waifu2x-Extension-GUI, QualityScaler | Separate from download queue/workflow |

## FrameForge wedge

1. Pure Python + CustomTkinter
2. Strictly sequential single-job downloads
3. SQLite WAL persistent queue
4. TXT/MD bulk import with preview + dedupe
5. Integrated local Real-ESRGAN / ONNX (DirectML preferred)
6. AMD-friendly / offline-first after setup
7. All user media under `%USERPROFILE%\Downloads\FrameForge\`
