"""SQLite connection helpers (WAL mode, thread-local).

GUI and the sequential worker must never share one sqlite3.Connection.
See docs/SQLITE_THREADING.md.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

BUSY_TIMEOUT_MS = 60_000
CONNECT_TIMEOUT_SEC = 60.0

TRANSIENT_SQLITE_SNIPPETS = (
    "database is locked",
    "database is busy",
    "cannot start a transaction",
    "cannot commit transaction",
    "no transaction is active",
)


def configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    # Autocommit: statements do not leave an implicit txn that breaks BEGIN IMMEDIATE.
    conn.isolation_level = None
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def connect(db_path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        timeout=CONNECT_TIMEOUT_SEC,
        check_same_thread=check_same_thread,
    )
    return configure_connection(conn)


def is_transient_sqlite(exc: BaseException | str) -> bool:
    """True for lock / nested-txn OperationalError (safe to retry, not a yt-dlp fail)."""
    if isinstance(exc, BaseException) and not isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        if "operationalerror" not in text and "sqlite" not in text:
            return False
    else:
        text = str(exc).lower()
    return any(snippet in text for snippet in TRANSIENT_SQLITE_SNIPPETS)


def retry_sqlite(op: Callable[[], T], *, attempts: int = 8, base_delay: float = 0.02) -> T:
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return op()
        except sqlite3.OperationalError as exc:
            last = exc
            if not is_transient_sqlite(exc) or i >= attempts - 1:
                raise
            time.sleep(base_delay * (2**i))
    assert last is not None
    raise last
