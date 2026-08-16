"""Move completed downloads into the local Library index."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.library.models import LibraryItem
from frameforge.library.paths import paths_equal, unique_dest
from frameforge.library.store import LibraryStore
from frameforge.library.taxonomy import INGEST_FOLDER, source_label_from_job
from frameforge.library.transfer import transfer_file

_YT_BRACKET_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")


@dataclass
class IngestResult:
    item: LibraryItem
    moved: bool
    source_path: Path
    dest_path: Path


def youtube_id_from_filename(name: str) -> str | None:
    match = _YT_BRACKET_RE.search(name)
    return match.group(1) if match else None


def index_download_media(roots: list[Path]) -> tuple[dict[str, Path], dict[str, Path]]:
    """Map basename and YouTube [id] → first video found under download roots."""
    by_name: dict[str, Path] = {}
    by_id: dict[str, Path] = {}
    for root in roots:
        folder = Path(root)
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not is_migrate_video(path):
                continue
            by_name.setdefault(path.name.lower(), path)
            vid = youtube_id_from_filename(path.name)
            if vid:
                by_id.setdefault(vid.lower(), path)
    return by_name, by_id


def _path_under_library(missing: Path, library_root: Path | None) -> bool:
    parts = {p.lower() for p in missing.parts}
    if INGEST_FOLDER.lower() in parts:
        return True
    if library_root is None:
        return False
    try:
        missing.resolve().relative_to(Path(library_root).resolve())
        return True
    except (ValueError, OSError):
        return False


def heal_job_download_paths(
    repo: JobRepository,
    *,
    download_roots: list[Path],
    library_root: Path | None = None,
) -> int:
    """If job paths point at missing Uncategorized/library files, restore the download-tree original.

    Does not copy. Used before Move so multi-GB work is not ordered by stale K: rows.
    """
    by_name, by_id = index_download_media(list(download_roots))
    healed = 0
    for job in repo.list_jobs("completed", include_queue_hidden=True):
        if job_media_file(job) is not None:
            continue
        for raw in (job.download_path, job.output_path):
            if not raw:
                continue
            missing = Path(raw)
            if missing.is_file():
                continue
            if not _path_under_library(missing, library_root):
                continue
            found = by_name.get(missing.name.lower())
            if found is None:
                vid = youtube_id_from_filename(missing.name)
                if vid:
                    hit = by_id.get(vid.lower())
                    if hit is not None and hit.suffix.lower() == missing.suffix.lower():
                        found = hit
            if found is None or not found.is_file():
                continue
            _update_job_paths(repo, job, missing, found)
            healed += 1
            break
    return healed


def job_media_file(job: Job) -> Path | None:
    for raw in (job.download_path, job.output_path):
        if not raw:
            continue
        path = Path(raw)
        if path.is_file() and path.stat().st_size > 0 and is_migrate_video(path):
            return path
    return None


def is_migrate_video(path: Path) -> bool:
    """Finished video only — never .part / aria2 / json."""
    from frameforge.library.paths import is_video_file

    if not is_video_file(path):
        return False
    name = path.name.lower()
    if name.endswith(".part") or ".part." in name or name.endswith(".aria2") or name.endswith(".ytdl"):
        return False
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def purge_missing_library_items(store: LibraryStore) -> int:
    """Drop index rows whose file is gone after heal. Does not delete media (there is none).

    Stale rows with a job_id must not block a later Move of the same download.
    """
    from frameforge.library.scan import heal_item, videos_by_filename

    by_name = videos_by_filename(store.root())
    dropped = 0
    for item in list(store.list_items(include_private=True)):
        healed = heal_item(store, item, by_name)
        if Path(healed.path).is_file():
            continue
        store.remove_item(item.id)
        dropped += 1
    return dropped


def completed_jobs_not_in_library(repo: JobRepository, store: LibraryStore) -> list[Job]:
    """Completed jobs with a file on disk that are not yet indexed."""
    pending: list[Job] = []
    for job in repo.list_jobs("completed", include_queue_hidden=True):
        if store.get_by_job_id(job.id):
            existing = store.get_by_job_id(job.id)
            if existing is not None and Path(existing.path).is_file():
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
    cancel: object | None = None,
    on_copy_progress: Callable[[int, int], None] | None = None,
    log_line: Callable[[str], None] | None = None,
    file_index: int | None = None,
    chunk_size: int | None = None,
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
        kwargs: dict = {
            "cancel": cancel,
            "on_progress": on_copy_progress,
            "log_line": log_line,
            "file_index": file_index,
        }
        if chunk_size is not None:
            kwargs["chunk_size"] = chunk_size
        dest = transfer_file(src, dest, **kwargs)
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


def move_path_into_library(
    store: LibraryStore,
    src: Path,
    *,
    dest_dir: Path | None = None,
    cancel: object | None = None,
    on_copy_progress: Callable[[int, int], None] | None = None,
    log_line: Callable[[str], None] | None = None,
    file_index: int | None = None,
    chunk_size: int | None = None,
) -> IngestResult:
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
        kwargs: dict = {
            "cancel": cancel,
            "on_progress": on_copy_progress,
            "log_line": log_line,
            "file_index": file_index,
        }
        if chunk_size is not None:
            kwargs["chunk_size"] = chunk_size
        dest = transfer_file(src, dest, **kwargs)
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
