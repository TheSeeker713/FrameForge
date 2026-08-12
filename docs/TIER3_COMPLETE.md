# Tier 3 complete

**Date:** 2026-08-12  
**Final suite:** **68 passed / 0 failed**

## Commits (main)

| Step | SHA | Summary |
|------|-----|---------|
| T3.1 | `01040ee` | Store source width/height on completed downloads |
| T3.2 | `cbf6496` | Highlight ≤720p completed jobs as `RECOMMENDED 2×` |
| T3.3 | `a206a1a` | **Select recommended** + upscale wiring; 4K still blocked |
| Doc | *(this commit)* | Tier 3 completion summary |

## How resolution is stored

After a successful download (and when a completed job already has a local `download_path`), FrameForge probes the file with existing ffprobe helpers and persists:

- Dedicated columns: `jobs.source_width`, `jobs.source_height` (SQLite migration version 2)
- APIs: `JobRepository.set_source_resolution()`, `JobRepository.probe_and_store_resolution()`
- Probe failure → columns left `NULL` (unknown); worker does not crash

`Job.upscale_recommended` / `Job.upscale_blocked` are derived from the stored height.

## Recommendation rule (≤720 highlighted)

| Source height | Upscale allowed? | Recommendation highlight? |
|---------------|------------------|---------------------------|
| Known and **≤ 720** | Yes | Yes — badge `RECOMMENDED 2×` + row accent |
| **721–2159** | Yes | No |
| **≥ 2160** | No (blocked) | No |
| Unknown (`NULL`) | Yes (until probe at upscale) | No |

Highlight survives queue refresh and selection changes. Recommendation is **UX only** — no auto-upscale.

## Block rule (≥2160 still blocked)

Existing Tier 2 guard remains:

- `assert_upscale_allowed()` / `MIN_BLOCK_HEIGHT = 2160`
- Failed jobs get: `Blocked: source is 4K/≥2160p (height=XXXX)`
- Queue may show `BLOCKED 4K+` styling when height is known and blocked

## Queue UX (T3.3)

1. Completed ≤720p jobs show as recommended in the list.
2. **Select recommended** multi-selects all currently recommended completed jobs.
3. **Upscale selected (2×)** still queues those jobs; worker remains sequential (one at a time).
4. ≥2160p jobs still refuse upscale with the clear blocked reason.

## Out of scope (unchanged)

- Auto-upscaling without user action
- Concurrent downloads
- Large unrelated UI redesigns
- New auth/cookie features beyond Tier 1
