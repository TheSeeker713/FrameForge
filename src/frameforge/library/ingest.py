"""Move completed downloads into the local Library index."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.library.models import LibraryItem
from frameforge.library.paths import paths_equal, unique_dest
from frameforge.library.store import LibraryStore
from frameforge.library.taxonomy import KIND_TYPE, source_label_from_job
from frameforge.library.transfer import transfer_file


@dataclass
class IngestResult:
    item: LibraryItem
    moved: bool
    source_path: Path
    dest_path: Path


def job_media_file(job: Job) -> Path | None:
    for raw in (job.download_path, job.output_path):
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            return path
    return None


def completed_jobs_not_in_library(repo: JobRepository, store: LibraryStore) -> list[Job]:
    """Completed jobs with a file on disk that are not yet indexed."""
    pending: list[Job] = []
    for job in repo.list_jobs("completed", include_queue_hidden=True):
        if store.get_by_job_id(job.id):
            continue
        path = job_media_file(job)
        if path is None:
            continue
        if store.get_by_path(path):
            continue
        pending.append(job)
    return pending


def _update_job_paths(repo: JobRepository, job: Job, old: Path, new: Path) -> None:
    kwargs: dict[str, str] = {}
    if job.download_path and paths_equal(job.download_path, old):
        kwargs["download_path"] = str(new)
    if job.output_path and paths_equal(job.output_path, old):
        kwargs["output_path"] = str(new)
    if kwargs:
        repo.set_paths(job.id, **kwargs)


def move_into_library(
    repo: JobRepository,
    store: LibraryStore,
    job: Job,
    *,
    dest_dir: Path | None = None,
) -> IngestResult:
    src = job_media_file(job)
    if src is None:
        raise FileNotFoundError(f"Job {job.id} has no local media file")
    folder = dest_dir or store.ingest_dir()
    folder.mkdir(parents=True, exist_ok=True)
    already_there = src.parent.resolve() == folder.resolve()
    if already_there:
        dest = src.resolve()
        moved = False
    else:
        dest = unique_dest(folder, src.name)
        dest = transfer_file(src, dest)
        moved = True
        _update_job_paths(repo, job, src, dest)
    uncat = store.uncategorized()
    item = store.add_item(
        path=dest,
        title=job.title,
        source=source_label_from_job(job),
        job_id=job.id,
        width=job.source_width,
        height=job.source_height,
        thumb_path=job.thumbnail_path,
        primary_collection_id=uncat.id,
    )
    if item.path != str(dest):
        item = store.update_item_path(item.id, dest)
    return IngestResult(item=item, moved=moved, source_path=src, dest_path=dest)


def move_path_into_library(store: LibraryStore, src: Path, *, dest_dir: Path | None = None) -> IngestResult:
    """Move or index a loose video file (no queue job) into Uncategorized."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(src)
    if store.get_by_path(src) is not None:
        item = store.get_by_path(src)
        assert item is not None
        return IngestResult(item=item, moved=False, source_path=src, dest_path=Path(item.path))
    folder = dest_dir or store.ingest_dir()
    folder.mkdir(parents=True, exist_ok=True)
    root = store.root()
    under_library = False
    if root is not None:
        try:
            src.resolve().relative_to(root.resolve())
            under_library = True
        except ValueError:
            under_library = False
    if under_library or src.parent.resolve() == folder.resolve():
        dest = src.resolve()
        moved = False
    else:
        dest = unique_dest(folder, src.name)
        dest = transfer_file(src, dest)
        moved = True
    uncat = store.uncategorized()
    item = store.add_item(
        path=dest,
        title=src.stem,
        source="Other",
        primary_collection_id=uncat.id,
    )
    if item.path != str(dest):
        item = store.update_item_path(item.id, dest)
    return IngestResult(item=item, moved=moved, source_path=src, dest_path=dest)


def ingest_completed_jobs(
    repo: JobRepository,
    store: LibraryStore,
    jobs: list[Job] | None = None,
    *,
    on_progress: Callable[[int, int, Job], None] | None = None,
) -> list[IngestResult]:
    """Synchronous helper for tests. GUI must use LibraryMoveRunner instead."""
    if store.root() is None:
        raise RuntimeError("Library root is not set")
    batch = jobs if jobs is not None else completed_jobs_not_in_library(repo, store)
    results: list[IngestResult] = []
    total = len(batch)
    for i, job in enumerate(batch, 1):
        if on_progress:
            on_progress(i, total, job)
        results.append(move_into_library(repo, store, job))
    return results


def assign_to_collection(
    repo: JobRepository,
    store: LibraryStore,
    item_ids: list[int],
    collection_id: int,
    *,
    make_primary: bool = True,
) -> list[LibraryItem]:
    """Tag items; when the collection uses a folder, move files there (primary path)."""
    col = store.get_collection(collection_id)
    updated: list[LibraryItem] = []
    dest_dir = store.collection_folder(col) if make_primary else None
    for item_id in item_ids:
        item = store.get(item_id)
        store.add_tag(item_id, collection_id)
        if make_primary and dest_dir is not None and col.uses_folder:
            src = Path(item.path)
            if src.is_file() and src.parent.resolve() != dest_dir.resolve():
                dest = unique_dest(dest_dir, src.name)
                dest = transfer_file(src, dest)
                store.update_item_path(item_id, dest)
                if item.job_id:
                    job = repo.get(item.job_id)
                    _update_job_paths(repo, job, src, dest)
            store.set_primary_collection(item_id, collection_id)
        elif make_primary and not col.uses_folder:
            store.set_primary_collection(item_id, collection_id)
        if make_primary:
            uncat = store.uncategorized()
            if collection_id != uncat.id:
                store.conn.execute(
                    "DELETE FROM library_item_collections WHERE item_id = ? AND collection_id = ?",
                    (item_id, uncat.id),
                )
                store.conn.commit()
        updated.append(store.get(item_id))
    return updated


def index_folder(store: LibraryStore, folder: Path) -> list[LibraryItem]:
    """Index video files in place (no move). Skips Private/."""
    from frameforge.library.paths import is_video_file
    from frameforge.library.taxonomy import PRIVATE_FOLDER

    folder = Path(folder)
    added: list[LibraryItem] = []
    if not folder.is_dir():
        return added
    for path in folder.rglob("*"):
        if not is_video_file(path):
            continue
        if PRIVATE_FOLDER.lower() in {p.lower() for p in path.parts}:
            continue
        if store.get_by_path(path):
            continue
        added.append(
            store.add_item(
                path=path,
                title=path.stem,
                source="Other",
            )
        )
    return added


def import_folder(store: LibraryStore, folder: Path) -> list[LibraryItem]:
    """Move video files into Uncategorized and index them."""
    from frameforge.library.paths import is_video_file
    from frameforge.library.taxonomy import PRIVATE_FOLDER

    folder = Path(folder)
    added: list[LibraryItem] = []
    if not folder.is_dir():
        return added
    dest_dir = store.ingest_dir()
    for path in list(folder.rglob("*")):
        if not is_video_file(path):
            continue
        if PRIVATE_FOLDER.lower() in {p.lower() for p in path.parts}:
            continue
        if store.get_by_path(path):
            continue
        dest = unique_dest(dest_dir, path.name)
        dest = transfer_file(path, dest)
        added.append(store.add_item(path=dest, title=path.stem, source="Other"))
    return added
