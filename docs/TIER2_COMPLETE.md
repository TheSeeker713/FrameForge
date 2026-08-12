# Tier 2 complete

**Date:** 2026-08-12  
**Final suite:** **59 passed / 0 failed**

## Commits (main)

| Step | Summary |
|------|---------|
| T2.1 | Upscale selected (2×) for completed downloads |
| T2.2 | Block upscale when source height ≥ 2160p |

## How to use Upscale selected (2×)

1. Download videos normally (Add/Import → **Download selected** / **Download all pending**).
2. When jobs show status `completed` and have a local file, multi-select them in the queue.
3. Click **Upscale selected (2×)**.
4. The worker runs one upscale at a time (sequential). Progress shows as `Upscaling #id (2×) — N%`.
5. Outputs land under `%USERPROFILE%\Downloads\FrameForge\upscaled\`.

You do **not** need “Upscale after download” enabled at enqueue time.

## 4K / ≥2160p block rule

Before upscale starts, FrameForge probes the source with ffprobe.

- If **height ≥ 2160**: upscale is **not** run. The job is marked `failed` with error:
  - `Blocked: source is 4K/≥2160p (height=XXXX)`
- The queue row shows the error text (`ERR:…`).
- Sources below 2160p upscale normally.

## What changed (code)

- `JobRepository.queue_for_upscale()` — completed + valid `download_path` → `download_completed` + `upscale=1`
- `SequentialWorker.request_upscale_ids()` — arms worker for upscale-only (does not claim pending downloads)
- GUI button **Upscale selected (2×)** + upscale progress label
- `frameforge.upscale.guards.assert_upscale_allowed()` enforced in handler and pipeline

## Remaining Tier 3 (not done)

- Extractor/site labels on add
- Open output folder / reveal file
- Harder cancel (kill yt-dlp/aria2c process)
- Richer per-job logs panel
