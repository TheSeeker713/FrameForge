"""Resolve a local thumbnail for a library item. Never raises."""

from __future__ import annotations

import logging
from pathlib import Path

from frameforge.library.models import LibraryItem
from frameforge.library.store import LibraryStore

log = logging.getLogger(__name__)


def ensure_library_thumbnail(store: LibraryStore, item: LibraryItem) -> LibraryItem:
    """Use an existing thumb, the job's thumb, or one frame from the video file."""
    current = Path(item.thumb_path) if item.thumb_path else None
    if current is not None and current.is_file() and current.stat().st_size > 32:
        return item
    if item.job_id:
        try:
            job = store.repo.get(item.job_id)
        except Exception:  # noqa: BLE001
            job = None
        raw = getattr(job, "thumbnail_path", None) if job is not None else None
        if raw and Path(str(raw)).is_file():
            try:
                return store.set_thumb_path(item.id, raw)
            except Exception:  # noqa: BLE001
                log.exception("Failed to store job thumbnail on library item %s", item.id)
    try:
        from frameforge.download.thumbnails import extract_video_still, thumbnail_path_for_job

        dest = thumbnail_path_for_job(item.job_id or (1_000_000 + int(item.id)))
        still = extract_video_still(item.path, dest)
        if still is not None and still.is_file():
            return store.set_thumb_path(item.id, still)
    except Exception:  # noqa: BLE001
        log.exception("Failed to extract a still for library item %s", item.id)
    return item
