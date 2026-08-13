# History v2

History is the durable memory of finished work. It lives in the same SQLite WAL `jobs` table as the queue. Clearing the live queue does **not** erase history.

See also [HISTORY.md](HISTORY.md) for the original filter/search contract.

## Durability

- Terminal statuses: `completed`, `failed`, `cancelled`.
- Soft-hide from the **queue** (`queue_hidden`) still appears in History.
- Soft-hide from **History** (`history_hidden`) hides the row from `list_history` only. The SQLite row remains.
- Restarting the app (new `JobRepository` on the same `frameforge.db`) returns the same visible history.

## Filters

History bar:

| Control | Behavior |
|---------|----------|
| **All / Completed / Failed** | Status chips (`All` includes cancelled). |
| **All domains** dropdown | Filter by `site_key` (or host / extractor substring). Populated from `history_domains()`. |
| Search | Case-insensitive substring on title, URL, or extractor. Enter to apply. |

API: `list_history(status=…, search=…, domain=…)`.

## Actions

| Button | Behavior |
|--------|----------|
| **Re-download selected** | Creates **new pending** jobs with the same URL/title/format/upscale flag. Original history rows are not modified. Does **not** arm the worker — use Download selected / Download all on the Queue tab. |
| **Clear selected** | Confirm, then `history_hidden` on those rows. Media files stay on disk. |
| **Clear all history** | Stronger confirm, then hide every visible history row. |

`retry_history_selected` is an alias of re-download (new pending jobs, not reset-in-place).

## Queue vs History

- Clear finished from the queue → rows remain in History.
- Clear from History → rows stay out of History until you would un-hide them in the DB; they are also gone from the live queue if they were already `queue_hidden`.
The v0.5 Flet History tab uses the same `list_history` / `reenqueue_as_pending` APIs. Re-download still does **not** arm the worker.
