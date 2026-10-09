# Site folders

New FrameForge jobs write media under **`downloads/<bucket>/<category>/`**. The queue, cookies, and models stay in the app home (`FRAMEFORGE_ROOT`, an existing install's saved home, or `%USERPROFILE%\Downloads\FrameForge`). The download folder is a separate first-run choice. Skip uses the Windows user folder `%USERPROFILE%\Downloads\FrameForge\downloads`. Choose a folder and videos go to `<picked>\FrameForge\downloads\<bucket>\<category>\`. On Windows, `cookies` and `database` are limited to the current user. Existing jobs that already have a non-legacy `download_output_dir` keep that path.

## Layout

| Output | Path |
|--------|------|
| Downloads (new jobs) | `<root>\downloads\<bucket>\<category>\` |
| Adult / pornographic | `<root>\downloads\porn\<category>\` |
| YouTube, X, Facebook | `<root>\downloads\social\youtube\<category>\`, `…\social\x.com\…`, `…\social\facebook\…` |
| Upscaled | `<root>\downloads\upscaled\<bucket>\` |
| Converted MP3 | `<root>\downloads\converted\<bucket>\` |
| Thumbnails | `<root>\thumbnails\` (global) |
| Cookies | `<root>\cookies\` (global) |
| SQLite DB | `<root>\database\frameforge.db` (global) |
| Temp / models / archive | unchanged global folders |

Default category when nothing else is known: `uncategorized`.

A category is chosen in this order: the import heading, then page metadata (`playlist_title`, `categories`, `genre`), then the first two words of a non-explicit title. An explicit sexual title does not become a folder name. Adult files stay under `downloads\porn\` either way.

Bulk import (`.txt`, `.md`, `.rtf`, `.doc`, `.docx`): a heading, a bold line, a `Category:` / `Subject:` label, or a plain line without a URL becomes the category for the links that follow. The folder name is the first two words. The host picks the bucket. A YouTube link and a news link under the same heading land in different site folders with the same category name.

Examples:

- `<root>\downloads\social\youtube\City council\`
- `<root>\downloads\bbc.com\City council\`
- `<root>\downloads\porn\Weather report\`
- `<root>\downloads\social\facebook\Market notes\`

## `site_key` and bucket rules

1. Prefer the job’s extractor label when it is not generic; otherwise parse the URL host.
2. Lowercase; strip leading `www.`.
3. Alias map (extensible in `frameforge.paths_site.SITE_ALIASES`):
   - `youtube.com`, `m.youtube.com`, `youtu.be`, `music.youtube.com`, extractor `Youtube` → `social/youtube`
   - `twitter.com`, `mobile.twitter.com`, `x.com` → `social/x.com`
   - `facebook.com`, `fb.watch`, `fb.com` → `social/facebook`
   - `reddit.com` / `old.reddit.com` → `reddit.com`
4. Adult hosts (`pornhub.com`, `eporner.com`, `xvideos.com`, …) keep a site_key for badges, but the **download bucket** is always `porn`. `downloads\eporner.com` is not a folder. A saved output dir under that name, or any other adult site folder, is remapped to `downloads\porn\<category>\` on retry.
5. Sanitize for Windows folders: strip `<>:"/\|?*` and control characters; trim spaces and trailing dots. Empty or reserved names → `other` (site) or `uncategorized` (category).
6. Directories are created on demand when a download, upscale, or convert actually writes.

On startup, leftover root-level site folders (old `youtube\`, `pornhub.com\`, …) are moved into `downloads/<bucket>/uncategorized` when they contain no in-flight `.part` / `.aria2` files.

Pause/resume keeps the persisted `download_output_dir` so partials stay in the same folder (legacy root paths are remapped for pending jobs).

Open folder / Reveal use the job’s stored file path. Queue rows show the site key as a badge when no higher-priority badge is present.
