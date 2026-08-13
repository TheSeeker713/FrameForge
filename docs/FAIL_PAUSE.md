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
| `ffmpeg` | ffmpeg/ffprobe errors | Mux / probe failed. |
| `blocked_4k` | 4K / ≥2160 blocked for upscale | Pick a lower source resolution. |
| `cancelled` | user cancel | Job was cancelled. |
| `unknown` | anything else | Unclassified failure. |

Suggested next steps are listed on the error panel (cookies / retry / wait / skip).

## Default policy

Setting **Pause queue on bot-check / login failures** (`fail_pause_on_auth`, default **ON**).

When a job fails with `auth_required` or `bot_check`:

1. The worker **disarms** on the worker thread (does not claim the next pending).
2. Remaining pending jobs stay pending.
3. A modal appears immediately with title, URL, cause, and raw error.

Optional `fail_pause_on_any=1` pauses on every failure (not exposed as a checkbox; default off).

Turn the default policy off in Settings if you want the bulk run to keep going after auth/bot failures.

## Modal actions

| Button | Effect |
|--------|--------|
| **Import from browser** | Firefox cookie import for the failed job’s URL. On success, offers **Retry this job and resume the queue**. |
| **Authenticate site** | Opens the existing authenticate / cookies.txt flow, prefilled with the job URL. |
| **Retry this job** | Resets that job to pending and arms download for that id only. |
| **Skip & resume queue** | Leaves the failed job failed; arms **Download all** for remaining pending. |
| **Stop queue** | Keeps the worker disarmed. |

You must choose an action. The worker does not silently continue failing the rest of the list.

The Flet UI calls the same handlers via `UiBridge.retry_job` / `handle_fail_pause_action` (see [UI_BRIDGE.md](UI_BRIDGE.md)). Retry that fails again hits the same disarm + `on_fail_pause` entrypoint.

## Gentle rate (optional)

The modal mentions Settings → **Gentle rate mode** (sleep interval + 2 MiB/s cap). It is **off by default**. Enable it after cookies work if bot checks keep returning. See [SPEED.md](SPEED.md).

## Invariants

Sequential single-active stage is unchanged. Enqueue still does not auto-start. Pause/resume of an in-flight job is separate from fail-pause of a finished failure.
