# Site folders

New FrameForge jobs write media under **`downloads/<bucket>/<category>/`** inside the app root. The root is `FRAMEFORGE_ROOT` when that variable is set, otherwise the path in `%APPDATA%\FrameForge\root.txt`, otherwise `%USERPROFILE%\Downloads\FrameForge\`. The database, cookies, and models stay at that root. On Windows, `cookies` and `database` are limited to the current user. Existing jobs that already have a non-legacy `download_output_dir` keep that path.

## Layout

| Output | Path |
|--------|------|
| Downloads (new jobs) | `<root>\downloads\<bucket>\<category>\` |
| Adult / pornographic | `<root>\downloads\porn\<category>\` |
| Streaming (YouTube, X, …) | `<root>\downloads\youtube\<category>\`, `…\x.com\…`, … |
| Upscaled | `<root>\downloads\upscaled\<bucket>\` |
| Converted MP3 | `<root>\downloads\converted\<bucket>\` |
| Thumbnails | `<root>\thumbnails\` (global) |
| Cookies | `<root>\cookies\` (global) |
| SQLite DB | `<root>\database\frameforge.db` (global) |
| Temp / models / archive | unchanged global folders |

Default category when none is set: `uncategorized`.

Bulk import (`.txt`, `.md`, `.rtf`, `.doc`, `.docx`): a heading, a bold line, a `Category:` / `Subject:` label, or a plain line without a URL becomes the category for the links that follow. The folder name is the first two words. The host picks the bucket. A YouTube link and a news link under the same heading land in different site folders with the same category name.

Examples:

- `<root>\downloads\youtube\City council\`
- `<root>\downloads\bbc.com\City council\`
- `<root>\downloads\porn\Weather report\`

## `site_key` and bucket rules

1. Prefer the job’s extractor label when it is not generic; otherwise parse the URL host.
2. Lowercase; strip leading `www.`.
3. Alias map (extensible in `frameforge.paths_site.SITE_ALIASES`):
   - `youtube.com`, `m.youtube.com`, `youtu.be`, `music.youtube.com`, extractor `Youtube` → `youtube`
   - `twitter.com`, `mobile.twitter.com`, `x.com` → `x.com`
   - `reddit.com` / `old.reddit.com` → `reddit.com`
4. Adult hosts (`pornhub.com`, `xvideos.com`, …) keep a site_key for badges, but the **download bucket** is always `porn`.
5. Sanitize for Windows folders: strip `<>:"/\|?*` and control characters; trim spaces and trailing dots. Empty or reserved names → `other` (site) or `uncategorized` (category).
6. Directories are created on demand when a download, upscale, or convert actually writes.

On startup, leftover root-level site folders (old `youtube\`, `pornhub.com\`, …) are moved into `downloads/<bucket>/uncategorized` when they contain no in-flight `.part` / `.aria2` files.

Pause/resume keeps the persisted `download_output_dir` so partials stay in the same folder (legacy root paths are remapped for pending jobs).

Open folder / Reveal use the job’s stored file path. Queue rows show the site key as a badge when no higher-priority badge is present.
