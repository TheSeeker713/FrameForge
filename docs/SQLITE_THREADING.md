# SQLite threading model

FrameForge keeps **WAL** mode and **one writer at a time at the job-stage level** (sequential worker). The GUI thread and the worker thread must **never share one `sqlite3.Connection`**.

## Choice: thread-local connections

`JobRepository` opens **one connection per thread** (`threading.local`), with:

- `check_same_thread=True` (Python sqlite3 default)
- `isolation_level=None` (autocommit — DML does not leave an implicit transaction)
- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=60000` and `sqlite3.connect(..., timeout=60)`

Claim still uses an explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` on **that thread’s** connection. Reads and progress writes retry on transient `OperationalError` (`database is locked` / nested-transaction messages).

`LibraryStore.conn` is a property that returns `repo.conn` (the caller’s thread-local connection), not a connection captured at store init.

A single-writer queue would also be correct; thread-local WAL is simpler for the existing Flet poll + sequential worker split.

## What went wrong (pre-0.6.5)

One `sqlite3.Connection` was created with `check_same_thread=False` and stored on `JobRepository`. The Flet UI thread listed jobs / wrote settings while the worker claimed with `BEGIN IMMEDIATE`.

Default sqlite3 isolation (`""`) starts an implicit transaction on DML. If the UI left that transaction open, the worker’s `BEGIN IMMEDIATE` raised:

```text
sqlite3.OperationalError: cannot start a transaction within a transaction
```

The worker loop treated that as a fatal handler error: `_fail_stuck_active_stages` marked the in-flight download **failed** with the raw sqlite string. `classify_error` mapped it to **`unknown`** (looked like a yt-dlp mystery). A single lock could cascade into “random” download failures.

## How to reproduce the old bug

On a throwaway on-disk DB (do not do this in FrameForge):

1. `conn = sqlite3.connect(path, check_same_thread=False)` — leave default `isolation_level`.
2. Thread A: `conn.execute("UPDATE jobs SET progress=1 WHERE id=1")` — do **not** commit.
3. Thread B: `conn.execute("BEGIN IMMEDIATE")` → nested-transaction `OperationalError`.
4. Old worker: catch-all → fail the `downloading` row with that message → category `unknown`.

v0.6.5: each thread has its own connection; autocommit means UI reads/writes do not hold an implicit txn; transient sqlite on claim/progress is retried; exhausted DB failures use category **`db_error`** (not fail-pause by default); `_fail_stuck_active_stages` no-ops when the reason is a transient sqlite message.

## Tests

`tests/test_sqlite_threading.py` — real files under `tmp_path`, concurrent `list_jobs` / `update_progress` / `claim_next_pending`, classifier, worker requeue.
