"""Background stills for library files. The UI thread only enqueues ids."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger(__name__)


class ThumbWorker:
    def __init__(self, db_path: str | Path, on_batch: Callable[[list[tuple[int, str]]], None] | None = None) -> None:
        self.db_path = Path(db_path)
        self.on_batch = on_batch
        workers = 3 if (os.cpu_count() or 1) >= 8 else 2
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="library-thumb")
        self._seen: set[int] = set()
        self._lock = threading.Lock()
        self._batch: list[tuple[int, str]] = []
        self._batch_lock = threading.Lock()
        self._flush_timer: threading.Timer | None = None

    def enqueue(self, file_ids: list[int]) -> None:
        for file_id in file_ids:
            with self._lock:
                if file_id in self._seen:
                    continue
                self._seen.add(file_id)
            self._pool.submit(self._one, int(file_id))

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _one(self, file_id: int) -> None:
        try:
            thumb = self._build(file_id)
        except Exception:  # noqa: BLE001
            log.exception("Thumbnail worker failed for file %s", file_id)
            return
        if thumb is None:
            return
        with self._batch_lock:
            self._batch.append((file_id, thumb))
            if self._flush_timer is None:
                self._flush_timer = threading.Timer(0.25, self._flush)
                self._flush_timer.daemon = True
                self._flush_timer.start()

    def _flush(self) -> None:
        with self._batch_lock:
            batch = self._batch
            self._batch = []
            self._flush_timer = None
        if batch and self.on_batch is not None:
            try:
                self.on_batch(batch)
            except Exception:  # noqa: BLE001
                log.exception("Thumbnail UI callback failed")

    def _build(self, file_id: int) -> str | None:
        from frameforge.db.repository import JobRepository
        from frameforge.download.invocation import ffmpeg_location
        from frameforge.library.probe import probe_file
        from frameforge.library.store import LibraryStore
        from frameforge.library.thumbs import (
            extract_library_thumb,
            file_stat_key,
            record_file_probe,
            save_thumb_row,
            thumb_file,
            thumb_is_current,
        )

        repo = JobRepository(self.db_path)
        try:
            store = LibraryStore(repo)
            row = store.conn.execute("SELECT * FROM library_files WHERE id = ?", (file_id,)).fetchone()
            if row is None or not row["present"]:
                return None
            keyed = file_stat_key(row["path"])
            if keyed is None:
                save_thumb_row(store, file_id, cache_key_value="missing", status="miss", error="file missing")
                return None
            key, _size, _mtime = keyed
            if thumb_is_current(store, file_id, key):
                existing = store.get_thumb(file_id)
                if existing and existing.status == "ok" and existing.thumb_path:
                    return existing.thumb_path
                return None
            if not row["probed_at"]:
                record_file_probe(store, file_id, probe_file(row["path"]))
                row = store.conn.execute("SELECT * FROM library_files WHERE id = ?", (file_id,)).fetchone()
            duration = None
            if row["duration_ms"] is not None:
                duration = float(row["duration_ms"]) / 1000.0
            ffmpeg = ffmpeg_location()
            if not ffmpeg:
                save_thumb_row(store, file_id, cache_key_value=key, status="miss", error="ffmpeg missing")
                return None
            dest = thumb_file(key)
            still = extract_library_thumb(Path(row["path"]), dest, duration=duration, ffmpeg=ffmpeg)
            if still is None:
                save_thumb_row(store, file_id, cache_key_value=key, status="miss", error="extract failed")
                return None
            save_thumb_row(store, file_id, cache_key_value=key, status="ok", thumb_path=str(still))
            store.conn.execute(
                """
                UPDATE library_items SET thumb_path = ?, date_modified = datetime('now')
                WHERE primary_file_id = ?
                """,
                (str(still), file_id),
            )
            store.conn.commit()
            return str(still)
        finally:
            repo.close()
