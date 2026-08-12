# Architecture

## Modules (grow by phase)

| Module | Role |
|--------|------|
| `frameforge.paths` | Resolve `%USERPROFILE%\Downloads\FrameForge\` and subdirs |
| `frameforge.env_check` | Probe Python packages and external tools |
| `frameforge.db` | SQLite WAL schema, migrations, repository (Phase 1) |
| `frameforge.queue` | Single sequential worker (Phase 1) |
| `frameforge.download` | yt-dlp wrapper, archive, TXT/MD bulk import (Phase 1) |
| `frameforge.upscale` | ONNX Real-ESRGAN tiling, stop/resume, audio remux (Phase 2) |
| `frameforge.pipeline` | Download → optional upscale orchestration (Phase 3) |
| `frameforge.convert` | ffmpeg MP3 convert stage (v0.4) |
| `frameforge.monitor` | psutil CPU/RAM sampler + upscale pressure policy (v0.4) |
| `frameforge.gui` | CustomTkinter dark UI (Phase 4) |

## Data layout

```
%USERPROFILE%\Downloads\FrameForge\
  youtube/       # new downloads for youtube (per-site; other sites similar)
  x.com/
  upscaled/<site_key>/
  converted/<site_key>/
  downloads/     # legacy flat downloads (not used for new jobs)
  temp/          # frames and intermediate files
  models/        # Real-ESRGAN ONNX weights
  archive/       # yt-dlp download archive artifacts
  cookies/       # Netscape cookie files (global)
  thumbnails/    # job thumbnails (global)
  frameforge.db  # SQLite WAL database
```

## Acceleration

1. Prefer `DmlExecutionProvider` via `onnxruntime-directml`
2. Fall back to `CPUExecutionProvider`
3. FFmpeg for demux/mux/encode; aria2c for fragment downloads of a **single** active job

## Sequential invariant

At most one job may be in an active media stage (`downloading`, `upscaling`, or `converting`) at any time. The single worker processes one job stage at a time. Aria2c multi-connection applies only to fragments of the current file — never a second video job.
