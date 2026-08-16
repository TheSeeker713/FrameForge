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
    errors: list[str] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)

    @property
    def summary(self) -> str:
        bits = [f"Moved {self.moved}", f"failed {self.failed}", f"skipped {self.skipped}"]
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


def run_library_move(
    repo: JobRepository,
    store: LibraryStore,
    jobs: list[Job] | None = None,
    *,
    cancel: threading.Event | None = None,
    on_progress: Callable[[MoveProgress], None] | None = None,
    between_files: Callable[[Job], None] | None = None,
) -> MoveReport:
    """Move completed downloads into the library. Continues after per-file errors.

    Checks *cancel* before each file. UI callers must run this off the Flet thread.
    """
    if store.root() is None:
        raise RuntimeError("Library root is not set")
    batch = jobs if jobs is not None else completed_jobs_not_in_library(repo, store)
    report = MoveReport()
    total = len(batch)
    for i, job in enumerate(batch, 1):
        if cancel is not None and cancel.is_set():
            report.cancelled = True
            report.skipped += total - i + 1
            break
        progress = MoveProgress(
            index=i,
            total=total,
            current_name=_job_label(job),
            moved=report.moved,
            failed=report.failed,
            skipped=report.skipped,
        )
        if on_progress:
            on_progress(progress)
        if between_files is not None:
            between_files(job)
        if cancel is not None and cancel.is_set():
            report.cancelled = True
            report.skipped += total - i + 1
            break
        try:
            result = move_into_library(repo, store, job)
            report.results.append(result)
            report.moved += 1
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort the batch
            report.failed += 1
            report.errors.append(f"#{job.id} {_job_label(job)}: {exc}")
            log.warning("Library move failed for job %s (%s): %s", job.id, _job_label(job), exc)
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
        self.between_files: Callable[[Job], None] | None = None
        self.job_ids: list[int] = []

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
        on_progress: Callable[[MoveProgress], None] | None = None,
        on_done: Callable[[MoveReport], None] | None = None,
    ) -> None:
        if self.running:
            raise RuntimeError("A library move is already running")
        self.cancel.clear()
        self.report = None
        self.job_ids = list(job_ids)

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
