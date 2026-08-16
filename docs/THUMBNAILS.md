# Thumbnails

FrameForge caches video thumbnails **locally** under:

`%USERPROFILE%\Downloads\FrameForge\thumbnails\<job_id>.jpg` (or `.png` / `.webp` when that is what the source served)

The path is stored on the job as `options_json.thumbnail_path`.

## When they are fetched

- On **Add URL** (metadata probe via yt-dlp `extract_info`, skip download)
- After a **successful download** if `info` includes a thumbnail URL

Failures are non-fatal: the job still enqueues and downloads.

## Privacy

Thumbnails are copies of public (or cookie-gated) preview images written to your disk. They are **not** uploaded anywhere. They are not committed to git. Delete the `thumbnails/` folder to clear the cache; jobs keep working without previews.

## UI

- Queue and History rows show a 48×36 preview (or a neutral placeholder). Decoded images are cached per path so the 1s GUI tick does not re-open large files.
- **Library** tab catalogs local files you moved or indexed. Queue and History rows still show a 48×36 preview. Click a completed Queue thumbnail to play.
