# UI bridge contract (v0.5)

Flet is a thin presentation layer. All download/queue/fail-pause commands go through `frameforge.ui_flet.bridge.UiBridge`, which talks to `JobRepository` + `SequentialWorker`. The worker stays off the UI thread.

## Rules

| Action | Arms worker? |
|--------|----------------|
| `enqueue_url` / bulk import / playlist enqueue / crash recovery | **No** |
| `download_selected` / `download_all_pending` / `retry_job` / fail-pause **Retry** / **Skip & resume** | **Yes** (explicit) |
| fail-pause **Stop** | Disarms |

Retry (failed card or modal) always calls `UiBridge.retry_job` → reset to pending + `request_download_ids([id])`. If that job fails again with `auth_required`, `bot_check`, or hard `unknown`, `maybe_fail_pause` disarms and `worker.on_fail_pause` fires the **same** UI entrypoint as the first bulk failure.

## Fail-pause categories

`FAIL_PAUSE_CATEGORIES` = `auth_required`, `bot_check`, `unknown`.

yt-dlp non-zero exits include a **stderr tail** (`format_ytdlp_exit_error`) so “exit code 1” plus “Sign in to confirm you’re not a bot” classifies as `bot_check`, not a bare unknown. Cause + `error_stderr_tail` are stored on the job and are never empty for failed jobs (`error_cause` falls back to a human sentence).

Network / not_available / ffmpeg do **not** pause the bulk queue unless `fail_pause_on_any=1`.

## Callbacks

`UiBridge.set_fail_pause_handler(fn)` — `fn(job, payload)` where `payload` is `fail_pause_payload(job)` (no Tk/Flet types). Flet marshals `fn` onto the page update path; CustomTkinter used `marshal_ui` the same way.

Fail-pause modal buttons call `UiBridge.handle_fail_pause_action(action_id, job_id, authenticate=…, import_browser=…, ask_retry_resume=…)`.

## Settings

`UiBridge.settings_open` is the single-instance flag (Phase C3). Enqueue never opens Settings.
