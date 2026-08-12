# History tab

Terminal jobs (`completed`, `failed`, `cancelled`) are queryable from the same SQLite WAL database as the active queue (`list_history`). Pending / downloading / upscaling rows are not history.

## Filters

- **All** — every visible terminal job
- **Completed** / **Failed** — status filter
- Search box — case-insensitive substring on title, URL, or extractor/site

Newest `finished_at` (else `updated_at`) first.

## Actions

| Action | Behavior |
|--------|----------|
| Open folder / Reveal file | Same as Queue; uses the selected job’s local path when it exists |
| Retry selected | Failed history rows reset to `pending` (existing retry semantics) |
| Hide selected | **Soft-hide** (`options_json.history_hidden = true`). Rows stay in SQLite and still appear on the Queue tab. Not a hard delete. |

## Persistence

History is SQLite-backed. Closing and reopening the app (or `JobRepository` on the same `frameforge.db`) still returns the same terminal jobs.

## Invariants

Sequential download/upscale and the manual-start model are unchanged. History queries do not alter `list_jobs` / `claim_next_pending`.
