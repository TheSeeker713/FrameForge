"""Background library file moves. Never call shutil.move on the UI thread."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from frameforge.db.repository import Job, JobRepository
from frameforge.library.ingest import (
    completed_jobs_not_in_library,
    job_media_file,
    move_into_library,
    move_path_into_library,
)
from frameforge.library.store import LibraryStore

log = logging.getLogger(__name__)


@dataclass
class MoveProgress:
    index: int
    total: int
    current_name: str
    moved: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False
    finished: bool = False


@dataclass
class MoveReport:
    moved: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False
    disk_found: int = 0
    errors: list[str] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)

    @property
    def summary(self) -> str:
        bits = [
            f"Moved {self.moved}",
            f"failed {self.failed}",
            f"skipped {self.skipped}",
            f"disk files {self.disk_found}",
        ]
        if self.cancelled:
            bits.append("cancelled")
        return ", ".join(bits)


def _job_label(job: Job) -> str:
    path = job_media_file(job)
    if path is not None:
        name = path.name
        return name if len(name) <= 80 else name[:77] + "…"
    title = str(job.title or job.url or f"#{job.id}")
    return title if len(title) <= 80 else title[:77] + "…"


def _label_for(job: Job | None, path: Path | None) -> str:
    if path is not None:
        name = path.name
        return name if len(name) <= 80 else name[:77] + "…"
    if job is not None:
        return _job_label(job)
    return "file"


def run_library_move(
    repo: JobRepository,
    store: LibraryStore,
    jobs: list[Job] | None = None,
    *,
    extra_paths: list[Path] | None = None,
    cancel: threading.Event | None = None,
    on_progress: Callable[[MoveProgress], None] | None = None,
    between_files: Callable[[Any], None] | None = None,
) -> MoveReport:
    """Move completed downloads and loose download-tree videos into the library.

    Checks *cancel* before each file. UI callers must run this off the Flet thread.
    """
    if store.root() is None:
        raise RuntimeError("Library root is not set")
    batch_jobs = jobs if jobs is not None else completed_jobs_not_in_library(repo, store)
    job_files = set()
    for job in batch_jobs:
        media = job_media_file(job)
        if media is not None:
            try:
                job_files.add(media.resolve())
            except OSError:
                job_files.add(media)
    disk: list[Path] = []
    for raw in extra_paths or []:
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in job_files:
            continue
        disk.append(path)
    report = MoveReport(disk_found=len(disk))
    work: list[tuple[Job | None, Path | None]] = [(j, None) for j in batch_jobs]
    work.extend((None, p) for p in disk)
    total = len(work)
    for i, (job, path) in enumerate(work, 1):
        if cancel is not None and cancel.is_set():
            report.cancelled = True
            report.skipped += total - i + 1
            break
        progress = MoveProgress(
            index=i,
            total=total,
            current_name=_label_for(job, path),
            moved=report.moved,
            failed=report.failed,
            skipped=report.skipped,
        )
        if on_progress:
            on_progress(progress)
        if between_files is not None:
            between_files(job if job is not None else path)
        if cancel is not None and cancel.is_set():
            report.cancelled = True
            report.skipped += total - i + 1
            break
        try:
            if job is not None:
                result = move_into_library(repo, store, job)
            else:
                assert path is not None
                result = move_path_into_library(store, path)
            report.results.append(result)
            report.moved += 1
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort the batch
            report.failed += 1
            label = _label_for(job, path)
            ident = f"#{job.id}" if job is not None else "disk"
            report.errors.append(f"{ident} {label}: {exc}")
            log.warning("Library move failed for %s (%s): %s", ident, label, exc)
    if on_progress:
        done = report.moved + report.failed
        on_progress(
            MoveProgress(
                index=done if done else total,
                total=total,
                current_name="",
                moved=report.moved,
                failed=report.failed,
                skipped=report.skipped,
                cancelled=report.cancelled,
                finished=True,
            )
        )
    return report


class LibraryMoveRunner:
    """Owns a daemon thread and a dedicated SQLite connection for the move."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.report: MoveReport | None = None
        self.between_files: Callable[[Any], None] | None = None
        self.job_ids: list[int] = []
        self.extra_paths: list[Path] = []

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def request_cancel(self) -> None:
        self.cancel.set()

    def join(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def start(
        self,
        job_ids: list[int],
        *,
        extra_paths: list[Path] | None = None,
        on_progress: Callable[[MoveProgress], None] | None = None,
        on_done: Callable[[MoveReport], None] | None = None,
    ) -> None:
        if self.running:
            raise RuntimeError("A library move is already running")
        self.cancel.clear()
        self.report = None
        self.job_ids = list(job_ids)
        self.extra_paths = [Path(p) for p in extra_paths or []]

        def _run() -> None:
            repo = JobRepository(self.db_path)
            store = LibraryStore(repo)
            try:
                jobs: list[Job] = []
                if self.job_ids:
                    for jid in self.job_ids:
                        try:
                            jobs.append(repo.get(jid))
                        except Exception:  # noqa: BLE001
                            continue
                else:
                    jobs = completed_jobs_not_in_library(repo, store)
                report = run_library_move(
                    repo,
                    store,
                    jobs,
                    extra_paths=self.extra_paths,
                    cancel=self.cancel,
                    on_progress=on_progress,
                    between_files=self.between_files,
                )
            except Exception as exc:  # noqa: BLE001
                report = MoveReport(failed=1, errors=[str(exc)])
            finally:
                try:
                    repo.close()
                except Exception:  # noqa: BLE001
                    pass
            self.report = report
            if on_done:
                on_done(report)

        self._thread = threading.Thread(target=_run, name="frameforge-library-move", daemon=True)
        self._thread.start()
