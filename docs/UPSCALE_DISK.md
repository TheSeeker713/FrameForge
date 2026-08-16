# Upscale disk guard (PNG pipeline)

The current upscaler is **not** streaming. ffmpeg extracts every frame to PNG under
`%USERPROFILE%\Downloads\FrameForge\temp\<job_key>\frames\`, ONNX writes 2× PNGs to
`temp\<job_key>\upscaled_frames\`, then ffmpeg muxes. Both trees exist at peak.

This document is the **disk precheck + cleanup** contract. It does **not** claim
hour-long 1080p upscales are safe, and it does **not** replace a later
ffmpeg-rawvideo → ONNX → encoder pipe.

## Formula

```
frames = ceil(duration_sec × fps)
if max_frames is set: frames = min(frames, max_frames)

PNG_BYTES_PER_PIXEL = 4     # worst-case RGB PNG (3 B/px + filter/deflate expansion)
scale                 = 2     # current ONNX 2× path
src = frames × width × height × 4
dst = frames × (width×2) × (height×2) × 4
estimated = src + dst
required  = estimated × 1.3   # SAFETY_MARGIN
```

`shutil.disk_usage` is taken on the volume of `temp_dir()` (typically `C:`).
If `required > free`, the job fails **before** extract with category `disk_space`.

Example: 1080p30 × 60 s → 1800 frames → source ~14.9 GB + 2× ~59.7 GB ≈ **74.6 GB**
estimated, **~97 GB** required after margin. A long 1080p job can fill the drive.

## Duration cap

Setting `upscale_max_duration_min` (default **15**). Clips longer than that are
refused with category `upscale_limit` until a streaming pipeline exists.
Set to `0` to disable the time cap (disk check still runs).

≥2160p is still blocked separately (`UpscaleBlockedError`). For 1080p the real
limit axis is **duration × disk**, not height.

## Cleanup

| Outcome | Frames tree |
|---------|-------------|
| Successful mux | `rmtree` the job dir (`frames`, `upscaled_frames`, checkpoint) |
| Terminal fail | same PNG trees deleted unless `upscale_keep_frames=1` |
| Pause / stop-resume (`DownloadCancelled` / `DownloadPaused`) | **kept** so checkpoint resume still works |

Startup / **Repair folders** sweeps `temp/<job>/{frames,upscaled_frames}` older than
`upscale_frames_orphan_hours` (default **24**). Never deletes `temp/dl` or `temp/junk`.

## Errors

- `disk_space` — human message includes **need** (required) vs **free**; Copy full
  report also has `disk_estimated_bytes` / `disk_required_bytes` / `disk_free_bytes`.
- `upscale_limit` — over the duration cap.
- Neither is classified as `unknown`.

## Settings

- **Max upscale duration (minutes)** — `upscale_max_duration_min`, default 15
- **Keep upscale PNG frames (debug)** — `upscale_keep_frames`, default off
