"""Background library file moves. Never call shutil.move on the UI thread."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import threading

from frameforge.db.repository import Job, JobRepository
from frameforge.library.ingest import (
    completed_jobs_not_in_library,
    is_migrate_video,
    job_media_file,
    move_into_library,
    move_path_into_library,
    purge_missing_library_items,
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
    log_path: str | None = None

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
        if self.log_path:
            bits.append(f"log {self.log_path}")
        return ", ".join(bits)


def _new_move_log() -> Path | None:
    try:
        from frameforge.paths import temp_dir

        folder = temp_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"library_move_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path.write_text("", encoding="utf-8")
        return path
    except OSError:
        log.exception("Could not create library move log")
        return None


def _log_line(path: Path | None, message: str) -> None:
    log.info("%s", message)
    if path is None:
        return
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
            fh.flush()
    except OSError:
        log.exception("Could not append library move log")


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
    log_file = _new_move_log()
    dropped = purge_missing_library_items(store)
    _log_line(log_file, f"start library_root={store.root()} purged_missing={dropped}")
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
        if not path.is_file() or not is_migrate_video(path):
            continue
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in job_files:
            continue
        disk.append(path)
    report = MoveReport(disk_found=len(disk), log_path=str(log_file) if log_file else None)
    _log_line(log_file, f"batch jobs={len(batch_jobs)} disk={len(disk)}")
    work: list[tuple[Job | None, Path | None]] = [(j, None) for j in batch_jobs]
    work.extend((None, p) for p in disk)
    total = len(work)

    def _emit(progress: MoveProgress) -> None:
        if not on_progress:
            return
        try:
            on_progress(progress)
        except Exception:  # noqa: BLE001 — UI ticks must not abort the batch
            log.exception("Library move progress callback failed at %s/%s", progress.index, progress.total)

    try:
        for i, (job, path) in enumerate(work, 1):
            if cancel is not None and cancel.is_set():
                report.cancelled = True
                report.skipped += total - i + 1
                break
            label = _label_for(job, path)
            ident = f"#{job.id}" if job is not None else "disk"
            _emit(
                MoveProgress(
                    index=i,
                    total=total,
                    current_name=label,
                    moved=report.moved,
                    failed=report.failed,
                    skipped=report.skipped,
                )
            )
            if between_files is not None:
                try:
                    between_files(job if job is not None else path)
                except Exception:  # noqa: BLE001
                    log.exception("Library move between_files hook failed for %s", ident)
            if cancel is not None and cancel.is_set():
                report.cancelled = True
                report.skipped += total - i + 1
                break
            src: Path | None = path if job is None else job_media_file(job)
            try:
                if job is not None:
                    result = move_into_library(repo, store, job)
                else:
                    assert path is not None
                    result = move_path_into_library(store, path)
                report.results.append(result)
                report.moved += 1
                _log_line(
                    log_file,
                    f"OK {ident} src={result.source_path} dst={result.dest_path}",
                )
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the batch
                report.failed += 1
                report.errors.append(f"{ident} {label}: {exc}")
                _log_line(
                    log_file,
                    f"FAIL {ident} src={src} error={exc}\n{traceback.format_exc()}",
                )
        _emit(
            MoveProgress(
                index=report.moved + report.failed if (report.moved + report.failed) else total,
                total=total,
                current_name="",
                moved=report.moved,
                failed=report.failed,
                skipped=report.skipped,
                cancelled=report.cancelled,
                finished=True,
            )
        )
    except Exception as exc:  # noqa: BLE001 — return partial report instead of raising
        log.exception("Library move batch aborted after moved=%s failed=%s", report.moved, report.failed)
        report.failed += 1
        report.errors.append(str(exc))
        _log_line(log_file, f"ABORT moved={report.moved} failed={report.failed} error={exc}\n{traceback.format_exc()}")
        _emit(
            MoveProgress(
                index=report.moved + report.failed,
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
            report = MoveReport()
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
                log.exception("LibraryMoveRunner crashed; preserving partial report moved=%s", report.moved)
                report.failed += 1
                report.errors.append(str(exc))
            finally:
                try:
                    repo.close()
                except Exception:  # noqa: BLE001
                    pass
            self.report = report
            if on_done:
                try:
                    on_done(report)
                except Exception:  # noqa: BLE001
                    log.exception("Library move on_done callback failed")

        self._thread = threading.Thread(target=_run, name="frameforge-library-move", daemon=True)
        self._thread.start()
