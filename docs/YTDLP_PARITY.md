# yt-dlp CLI parity

Terminal `yt-dlp URL` succeeding while FrameForge fails the same URL as
**unknown** is treated as a command-line mismatch until proven otherwise.

## How the app invokes yt-dlp

The GUI worker uses a **killable subprocess**, not the in-process `YoutubeDL`
API:

```
<venv python> -m yt_dlp [flags…] URL
```

That is **not** the same binary as `yt-dlp` on PATH. Both versions are stored
on the job (`ytdlp_invocation.yt_dlp_version` vs `yt_dlp_path_version`).

Rebuild the exact argv without downloading:

```python
from frameforge.download.ytdlp import YtDlpDownloader
dl = YtDlpDownloader(output_dir=…, archive_file=…)
print(dl.describe_cli_invocation(url))
```

Every download job persists `options_json.ytdlp_invocation`:

| Field | Meaning |
|-------|---------|
| `argv` | Full argument list passed to `Popen` |
| `cwd` | Working directory (`output_dir`, not the GUI cwd) |
| `output_template` | `-o` template |
| `cookies` | Netscape cookie file or `null` |
| `cookies_attached` | True only when a valid cookie file was passed |
| `concurrent_fragments` | `-N` / `--concurrent-fragments` (default 8) |
| `throttled_rate` | `--throttled-rate` (default `100K`) |
| `http_chunk_size` | `--http-chunk-size` (default `10M`) |
| `aria2c` | Whether `--downloader aria2c` was actually added |
| `aria2_args` | Exact aria2c extra args (`-x 16 -s 16 …`) or `null` |
| `player_client` | `--extractor-args` value, or `null` |
| `impersonate` | `--impersonate` client (`chrome` / `edge`), or `null` |
| `js_runtimes` | `--js-runtimes` value when Deno/Node was found |
| `format` | `-f` selector |
| `ffmpeg_location` | Resolved `ffmpeg` path, if on PATH |
| `env_overrides` | PATH prepends for ffmpeg/aria2c |
| `yt_dlp_version` | Package inside the app/venv |
| `yt_dlp_path_version` | `yt-dlp --version` from PATH |
| `python` | `sys.executable` |
| `returncode` | Process exit code (subprocess path) |
| `stderr_empty` | True when no stderr/stdout tail was captured |

Same job also persists:

| Field | Meaning |
|-------|---------|
| `download_method` | `aria2c` or `native` for the attempt that finished (or last attempt) |
| `aria2_fallback_native` | True when attempt 1 used aria2 and attempt 2 ran native |
| `download_attempt` | `1` (aria2/default) or `2` (native fallback) |

If stderr is empty, the job error is:

`yt-dlp exited with code N` + `no stderr; see invocation log` + `argv: …`

## Aria2 CDN 403 → native fallback (v0.5.8)

Keep aria2 as the preferred path when it is on PATH (including YouTube).

When yt-dlp reports **aria2c exit 22** / googlevideo **HTTP 403**, FrameForge does **not** mark the job failed on that first try and does **not** classify it as `ffmpeg` (argv often contains `--ffmpeg-location`). It retries the **same job** once without `--downloader aria2c`. Cancel still kills the active attempt’s process tree.

Fail-pause does **not** fire for `aria2_forbidden`. The queue pauses only after a **final** failure whose category is in the fail-pause set.

## Cancel vs “Cancelled by the uploader”

User **Cancel** is `DownloadCancelled` (process-tree kill) or a job already in status `cancelled`. The worker does **not** scan `str(exc)` for the word “cancelled”.

yt-dlp messages such as “This live event was Cancelled by the uploader” are classified as **`not_available`**: the job is **failed**, the stderr is kept, and Retry failed remains available. That is not user-cancelled and does not fail-pause. See [FAIL_PAUSE.md](FAIL_PAUSE.md).

## Fixes in 0.5.4

1. **Sticky cookies** — `cookiefile` is assigned every job, including `None`.
   A previous YouTube cookie file is not reused for the next URL.
2. **Empty/invalid `--cookies`** — only Netscape files with at least one cookie
   row are passed. Header-only stubs are omitted.
3. **aria2c** — used only when `aria2c` is on PATH. Missing aria2c used to make
   yt-dlp fail while a plain CLI download succeeded.
4. **cwd** — subprocess runs in the job output directory, not Explorer/System32.
5. **ffmpeg** — `--ffmpeg-location` is set when `ffmpeg` is on PATH; PATH is
   prepended with the directories of ffmpeg/ffprobe/aria2c.
6. **stderr** — captured on a dedicated pipe (not merged away) and folded into
   the error tail. Empty tails still store argv + return code.

## Remaining deliberate differences vs a bare `yt-dlp URL`

These are still present and logged:

- `python -m yt_dlp` (venv package) instead of the PATH `yt-dlp.exe`
- `-f bv*+ba/b` instead of yt-dlp’s default format
- `--download-archive` (FrameForge archive file)
- `--no-playlist`, `--merge-output-format mp4`, `--write-info-json`, `--write-thumbnail`
- YouTube `--extractor-args youtube:player_client=android_vr,tv_downgraded,web_embedded,web_safari` (Settings can restore yt-dlp defaults)
- `--impersonate chrome` on PornHub / related MindGeek hosts when curl_cffi targets exist (Settings Auto / Always / Off)
- `--js-runtimes deno:<path>` or `node:<path>` when a JS runtime is found
- aria2c **when installed** (`-x 16 -s 16 -k 1M …`) — CLI usually has none
- `--concurrent-fragments 8`, `--throttled-rate 100K`, `--http-chunk-size 10M`

If a URL still fails only in the app, copy the job’s invocation snapshot and
run that argv in a terminal from the recorded `cwd`.

## PornHub impersonate (v0.6.8)

Adult hosts need `--impersonate chrome` plus `cookies\pornhub.com.txt`. Job-70-style
HTTP 410 without impersonate is `impersonation_missing`, not `unknown`. Pin
`curl_cffi==0.13.0` with yt-dlp 2026.07.04; do not jump curl_cffi to 0.16.x alone.
See [ADULT_SITES.md](ADULT_SITES.md).
