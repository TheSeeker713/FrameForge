# Site folders

New FrameForge jobs write media into **per-site subfolders** under `%USERPROFILE%\Downloads\FrameForge\`. Existing jobs that already have a flat `download_output_dir` keep that path (no mass migration).

## Layout

| Output | Path |
|--------|------|
| Downloads (new jobs) | `Downloads\FrameForge\<site_key>\` |
| Upscaled | `Downloads\FrameForge\upscaled\<site_key>\` |
| Converted MP3 | `Downloads\FrameForge\converted\<site_key>\` |
| Thumbnails | `Downloads\FrameForge\thumbnails\` (global) |
| Cookies | `Downloads\FrameForge\cookies\` (global) |
| SQLite DB | `Downloads\FrameForge\frameforge.db` (global) |
| Temp / models / archive | unchanged global folders |

Examples:

- `%USERPROFILE%\Downloads\FrameForge\youtube\`
- `%USERPROFILE%\Downloads\FrameForge\x.com\`
- `%USERPROFILE%\Downloads\FrameForge\reddit.com\`
- `%USERPROFILE%\Downloads\FrameForge\other\` (unparseable URL)

## `site_key` rules

1. Prefer the job’s extractor label when it is not generic; otherwise parse the URL host.
2. Lowercase; strip leading `www.`.
3. Alias map (extensible in `frameforge.paths_site.SITE_ALIASES`):
   - `youtube.com`, `m.youtube.com`, `youtu.be`, `music.youtube.com`, extractor `Youtube` → `youtube`
   - `twitter.com`, `mobile.twitter.com`, `x.com` → `x.com`
   - `reddit.com` / `old.reddit.com` → `reddit.com`
4. Sanitize for Windows folders: strip `<>:"/\|?*` and control characters; trim spaces and trailing dots. Empty or reserved names (`downloads`, `upscaled`, `converted`, `temp`, `models`, `archive`, `cookies`, `thumbnails`) → `other`.
5. Directories are created on demand when a download, upscale, or convert actually writes.

Pause/resume keeps the persisted `download_output_dir` so partials stay in the same site folder.

Open folder / Reveal use the job’s stored file path, so they follow site subfolders automatically. Queue rows show the site key as a badge when no higher-priority badge (paused / recommended / playlist) is present.
