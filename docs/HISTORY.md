# History tab

Terminal jobs (`completed`, `failed`, `cancelled`) are queryable from the same SQLite WAL database as the active queue (`list_history`). Pending / downloading / upscaling rows are not history.

v0.4.2 adds domain filters, re-download as a **new pending** job, and clear-from-history. See [HISTORY_V2.md](HISTORY_V2.md). Clearing the live queue does not erase History ([QUEUE_CLEAR.md](QUEUE_CLEAR.md)).

## Filters

- **All** — every visible terminal job
- **Completed** / **Failed** — status filter
- Domain dropdown — `site_key` / host (see [HISTORY_V2.md](HISTORY_V2.md))
- Search box — case-insensitive substring on title, URL, or extractor/site

Newest `finished_at` (else `updated_at`) first.

## Actions

| Action | Behavior |
|--------|----------|
| Open folder / Reveal file | Same as Queue; uses the selected job’s local path when it exists |
| Re-download selected | New pending job with the same URL (does not clobber the history row; does not arm the worker) |
| Clear selected / Clear all history | **Soft-hide** (`options_json.history_hidden = true`). Rows stay in SQLite. Media files are not deleted. |

## Persistence

History is SQLite-backed. Closing and reopening the app (or `JobRepository` on the same `frameforge.db`) still returns the same terminal jobs.

## Invariants

Sequential download/upscale and the manual-start model are unchanged. History queries do not alter `list_jobs` / `claim_next_pending`.
