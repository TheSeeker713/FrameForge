# Fail-pause (bulk safety)

After a stretch of successful downloads, sites often throw bot-check, login, or rate errors. FrameForge classifies the failure, shows a human cause, and — for serious categories — **pauses the queue** so the rest of a bulk list is not burned.

## Categories

Stored on the job (`error_category`, `error_cause`, `error_actions`) and shown in the error panel.

| Category | Typical signals | Cause (plain language) |
|----------|-----------------|------------------------|
| `auth_required` | login / cookies / sign in | Site wants you signed in. |
| `bot_check` | “not a bot”, recaptcha, unusual traffic | Site thinks this is automated. |
| `rate_limited` | HTTP 429, too many requests | Site is slowing you down. |
| `not_available` | private, removed, 404 | Video cannot be downloaded. |
| `network` | timeout, DNS, connection reset | Network interrupted the download. |
| `ffmpeg` | ffmpeg/ffprobe errors (not `--ffmpeg-location` in argv) | Mux / probe failed. |
| `aria2_forbidden` | aria2c exit 22 / googlevideo HTTP 403 | CDN blocked the fast downloader. |
| `blocked_4k` | 4K / ≥2160 blocked for upscale | Pick a lower source resolution. |
| `cancelled` | user cancel (`DownloadCancelled` or status `cancelled`) | Job was cancelled. |
| `js_runtime` | n-challenge / EJS / only images | Deno + yt-dlp-ejs missing or failed. |
| `output_missing` | exit 0 but no file / archive orphan | File missing on disk after a “successful” download. |
| `unknown` | anything else | Unclassified failure. |

Suggested next steps are listed on the error panel (cookies / retry / wait / skip).

## Default policy

Setting **Pause queue on bot-check / login failures** (`fail_pause_on_auth`, default **ON**).

When a job fails with `auth_required`, `bot_check`, `js_runtime`, `output_missing`, or hard `unknown`:

1. The worker **halts** (`halt_after_fail`): disarms **and** latches so a stale
   `_armed` flag cannot claim the next pending.
2. Remaining pending jobs stay pending.
3. A modal appears immediately with title, URL, cause, and raw error.

`_process_one` refuses to claim while the halt latch is set. Only an explicit
user action (`Download all`, Retry, Skip & resume, Resume paused) clears it.

If the download handler marks a job `failed` without raising, the worker still
runs fail-pause instead of promoting that row to `completed`.

Optional `fail_pause_on_any=1` pauses on every failure (not exposed as a checkbox; default off).

`output_missing` pauses the bulk queue **without** cookie import. Actions are Retry (force re-download if the yt-dlp archive is stale), Open folder, Skip & resume, Stop, and Copy report. See [OUTPUT_PATH.md](OUTPUT_PATH.md).

`aria2_forbidden` is **not** a fail-pause category.

**User cancel vs yt-dlp “Cancelled”:** the worker never treats English in `str(exc)` as a cancel. Only an explicit user cancel/pause (status already `cancelled`/`paused`) or typed `DownloadCancelled` / `DownloadPaused` preserve those statuses. yt-dlp stderr such as “This live event was Cancelled by the uploader” is **`not_available`** (job **failed**, error text kept, Retry failed works). It is not user-cancelled and does not fail-pause the bulk queue. See [YTDLP_PARITY.md](YTDLP_PARITY.md).

Turn the default policy off in Settings if you want the bulk run to keep going after auth/bot failures.

## Modal actions

| Button | Effect |
|--------|--------|
| **Import from Firefox / browser** | Firefox-first cookie import. Chrome DPAPI is not a FrameForge fix. |
| **Import cookies.txt** | Opens authenticate / Netscape file import, prefilled with the job URL. |
| **Retry this job** | Resets that job to pending and arms download for that id only. |
| **Skip & resume queue** | Leaves the failed job failed; arms **Download all** for remaining pending. |
| **Stop queue** | Keeps the worker disarmed. |

`js_runtime` pauses omit cookie import and tell you to install Deno + yt-dlp-ejs instead.

You must choose an action. The worker does not silently continue failing the rest of the list.

The Flet UI calls the same handlers via `UiBridge.retry_job` / `handle_fail_pause_action` (see [UI_BRIDGE.md](UI_BRIDGE.md)). Retry that fails again hits the same disarm + `on_fail_pause` entrypoint.

After **Import from browser**, cookies are **validated** before resume. Success offers **Retry this job and resume the queue**. Failure keeps the modal open. See [BOT_CHECK_PLAYBOOK.md](BOT_CHECK_PLAYBOOK.md).

## Gentle rate (optional)

Settings → **Gentle rate mode** (sleep interval + 2 MiB/s cap) is **off by default**. After a successful bot-check cookie recovery, FrameForge enables a **short cooldown** for the next 3 jobs (`gentle_jobs_left`) without flipping the permanent setting. See [SPEED.md](SPEED.md).

## Invariants

Sequential single-active stage is unchanged. Enqueue still does not auto-start. Pause/resume of an in-flight job is separate from fail-pause of a finished failure.
