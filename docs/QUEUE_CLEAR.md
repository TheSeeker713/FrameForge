# Queue clear

The live Queue tab is the work list, not the long-term record. Clearing a job from the queue never deletes media files on disk (no “also delete files” option in this release).

## Clear selected

Queue button **Clear selected**. Enabled when the selection includes at least one job that is not an in-flight media stage (`downloading` / `upscaling` / `converting`). Pause or cancel those first.

| Status | What happens |
|--------|----------------|
| `completed`, `failed`, `cancelled` | Soft-hide: `options_json.queue_hidden = true`. The row stays in SQLite so History still lists it. |
| `pending`, `paused`, and other non-active rows | Hard-delete the SQLite row only. |
| Active download / upscale / convert | Skipped. |

API: `JobRepository.clear_from_queue(ids)`.

## Clear finished

Queue button **Clear finished**. Confirms, then hides every **completed + failed + cancelled** job currently visible in the queue. Pending, paused, and in-flight jobs are unchanged.

Repository helpers:

- `clear_finished_from_queue()` — completed, failed, cancelled
- `clear_completed_from_queue()` — completed only
- `clear_failed_from_queue()` — failed only

## Visibility

`list_jobs`, `count_by_status`, `claim_next_pending`, `claim_next_convert`, and `url_in_queue` ignore `queue_hidden` rows. History queries do not.

## Invariants

Sequential single-active stage is unchanged. Enqueue still does not auto-start. Pause/resume and cancel are separate from clear.
