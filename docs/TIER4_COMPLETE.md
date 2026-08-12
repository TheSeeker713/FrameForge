# Tier 4 complete

**Date:** 2026-08-12  
**Final suite:** **81 passed / 0 failed**

## Commits (main)

| Step | SHA | Summary |
|------|-----|---------|
| T4.1 | `588a751` | Hard cancel kills yt-dlp/aria2c/ffmpeg process tree |
| T4.2 | `0191fcf` | Extractor/site label on add + queue display |
| T4.3 | `950431c` | Open folder / Reveal file |
| T4.4 | `22cdcb6` | Per-job error detail panel |
| Doc | *(this commit)* | Tier 4 completion summary |

## Hard cancel (T4.1)

- Downloads that go through the worker run yt-dlp as a **killable subprocess** (with aria2c as external downloader when enabled).
- `ProcessRegistry` tracks the active PID per job; `SequentialWorker.cancel_job()` sets status `cancelled` and runs Windows `taskkill /F /T /PID …` (process tree).
- FFmpeg steps in the upscale path also register PIDs when a registry is provided.
- Cancel exceptions are preserved as `cancelled` (not overwritten to `failed`).
- Non-active jobs still cancel safely via status-only update.

## Extractor / site on add (T4.2)

- Column: `jobs.extractor` (migration version 3).
- **Add URL:** lightweight `extract_info` (skip download) → title + extractor; on failure falls back to hostname site label and still enqueues.
- **Bulk import:** inexpensive hostname label only (no per-URL network probe).
- Queue rows show `[extractor]` when present.

## Open folder / Reveal file (T4.3)

- Buttons: **Open folder**, **Reveal file**.
- Prefer `output_path`, then `download_path`.
- Windows Explorer: open directory, or `/select,` for reveal.
- Missing/invalid path → clear error dialog; no crash.

## Error panel (T4.4)

- Dedicated **Job errors / details** text area under the queue.
- Shows full `job.error` for the selected job (download failures, cancel notes, Tier 2 ≥2160 block reasons, etc.).
- Empty/neutral when nothing selected or the job has no error; updates on selection and refresh.

## Out of scope (unchanged)

- Full product re-audit
- Auto-upscale
- Concurrent downloads
- Major visual redesign beyond these four items
