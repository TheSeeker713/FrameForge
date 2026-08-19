# Upscale disk + chunked pipeline

The default upscaler is **chunked**, not a full-film PNG dump. ffmpeg extracts
**one chunk** of frames (default **128**, setting `upscale_chunk_frames`, 64–256),
ONNX writes 2× PNGs for that chunk, ffmpeg encodes a video segment, then the PNG
trees are deleted before the next chunk. Segments are concatenated and the
**original audio** is muxed at the end.

This is still not a rawvideo pipe. Peak temp is **one chunk** of PNGs plus encoded
segments (small vs PNG). A 41-minute clip must **not** materialize ~hours of PNG.

Do **not** claim Real-ESRGAN quality when only `frameforge_smoke_identity.onnx`
is present (Identity + OpenCV 2× interpolation).

## Formula (one chunk)

```
chunk_frames = min(configured_chunk, total_frames, max_frames if set)

PNG_BYTES_PER_PIXEL = 4
scale                 = 2
src = chunk_frames × width × height × 4
dst = chunk_frames × (width×2) × (height×2) × 4
estimated = src + dst
required  = estimated × 1.3   # SAFETY_MARGIN
```

`shutil.disk_usage` is taken on the volume of `temp_dir()`.
If `required > free`, the job fails **before** extract with category `disk_space`.
Refuse only if **one chunk** cannot fit — not the full film.

Example: 1080p30 × 128-frame chunk → source ~1.0 GB + 2× ~4.2 GB ≈ **5.3 GB**
estimated, **~6.8 GB** required after margin. A 41-minute 1080p job no longer
needs ~tens of GB of PNG for the whole timeline.

## Duration

There is **no hard duration cap** on the chunked path (`upscale_max_duration_min`
default 15 is a **soft warning** in logs / Settings). Set to `0` to disable the
warning. Very long jobs (40+ min 1080p on Radeon 680M iGPU) can take **many
hours** of GPU/CPU time even though disk stays bounded to one chunk.

≥2160p is still blocked (`UpscaleBlockedError`).

## Models

`%USERPROFILE%\Downloads\FrameForge\models\` is created on startup. If it is
empty, FrameForge logs once and tries to write a **smoke Identity ONNX** so the
GUI can start. Upscale with only smoke is interpolation, not Real-ESRGAN.

```powershell
python .\scripts\create_smoke_onnx.py
python .\scripts\download_models.py   # Real-ESRGAN when network allows
```

Missing model at job time: category `upscale_config` (never a startup traceback).

## Cleanup

| Outcome | Temp |
|---------|------|
| Successful mux | `rmtree` the job dir (chunk PNGs, segments, checkpoint) |
| Terminal fail | PNG trees deleted unless `upscale_keep_frames=1` |
| Pause / cancel | **kept** (completed segments + current-chunk PNGs + checkpoint) so resume works |

Startup / **Repair folders** sweeps `temp/<job>/{frames,upscaled_frames}` older than
`upscale_frames_orphan_hours` (default **24**). Never deletes `temp/dl` or `temp/junk`.

## Errors

- `disk_space` — human message includes **need** (one chunk) vs **free**.
- `upscale_config` — no ONNX under the models dir.
- `upscale_limit` — legacy hard-cap message still classifies (chunked path does not raise it).
- None of these is `unknown`.

## Settings

- **Upscale chunk frames** — `upscale_chunk_frames`, default 128 (64–256)
- **Warn if clip longer than (minutes)** — `upscale_max_duration_min`, default 15, **not a refuse**
- **Keep last upscale PNG chunk (debug)** — `upscale_keep_frames`, default off
