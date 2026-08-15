# Queue clear

The live Queue tab is the work list, not the long-term record. Clearing a job from the queue never deletes media files on disk (no “also delete files” option in this release).

## Clear selected

Queue button **Clear selected**. Enabled when the selection includes at least one job that is not an in-flight media stage (`downloading` / `upscaling` / `converting`). Pause or cancel those first.

| Status | What happens |
|--------|----------------|
| Any clearable row (pending, paused, completed, failed, cancelled, …) | Soft-hide: `options_json.queue_hidden = true`. SQLite row stays so **Undo** can restore it. |
| Active download / upscale / convert | Skipped. |

Media files are never deleted. v0.5.3 stopped hard-deleting pending rows so Undo works.

API: `JobRepository.clear_from_queue(ids)` / `UiBridge.clear_selected`.

## Clear finished

Queue button **Clear finished**. Hides every **completed + failed + cancelled** job currently visible in the queue. **Never** hides or removes `pending`, `paused`, `downloading`, `upscaling`, `converting` (v0.5.3 field bug: a prior path could hard-delete non-finished rows).

Repository helpers:

- `clear_finished_from_queue()` — completed, failed, cancelled only (does **not** call `clear_from_queue`)
- `clear_completed_from_queue()` — completed only
- `clear_failed_from_queue()` — failed only

## Undo

After Clear finished / Clear selected / History clear, FrameForge keeps an in-memory stack (last 5). **Undo** restores previous `queue_hidden` / `history_hidden` flags only. Toast: “Cleared N items — Undo”.

## Visibility

`list_jobs`, `count_by_status`, `claim_next_pending`, `claim_next_convert`, and `url_in_queue` ignore `queue_hidden` rows. History queries do not.

## Invariants

Sequential single-active stage is unchanged. Enqueue still does not auto-start. Pause/resume and cancel are separate from clear.
