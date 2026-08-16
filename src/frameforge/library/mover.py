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
    _update_job_paths,
    completed_jobs_not_in_library,
    heal_job_download_paths,
    is_migrate_video,
    job_media_file,
    move_into_library,
    move_path_into_library,
    purge_missing_library_items,
)
from frameforge.library.store import LibraryStore
from frameforge.library.transfer import TransferCancelled

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
    bytes_copied: int = 0
    bytes_total: int = 0
    copying: bool = False


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


def _resolve_media(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _copy_label(name: str, size: int) -> str:
    if size >= 1_000_000_000:
        return f"{name} ({size / 1_000_000_000:.1f} GB)"
    if size >= 1_000_000:
        return f"{name} ({size / 1_000_000:.1f} MB)"
    return name


def build_move_work(
    jobs: list[Job],
    extra_paths: list[Path] | None = None,
) -> list[tuple[Job | None, list[Job], Path | None, Path, int]]:
    """Dedupe by resolved source path. Returns (primary_job, extra_jobs, disk_path, src, size)."""
    groups: dict[str, tuple[Job | None, list[Job], Path | None, Path, int]] = {}
    order: list[str] = []
    for job in jobs:
        media = job_media_file(job)
        if media is None:
            key = f"missing:{job.id}"
            groups[key] = (job, [], None, Path(job.download_path or job.output_path or "."), 0)
            order.append(key)
            continue
        src = _resolve_media(media)
        key = str(src).lower()
        if key in groups:
            primary, extras, disk, path, size = groups[key]
            extras.append(job)
            groups[key] = (primary, extras, disk, path, size)
            continue
        groups[key] = (job, [], None, src, _file_size(src))
        order.append(key)
    job_keys = set(groups)
    for raw in extra_paths or []:
        path = Path(raw)
        if not path.is_file() or not is_migrate_video(path):
            continue
        src = _resolve_media(path)
        key = str(src).lower()
        if key in job_keys or key in groups:
            continue
        groups[key] = (None, [], path, src, _file_size(src))
        order.append(key)
    items = [groups[k] for k in order]
    items.sort(key=lambda row: (row[4], row[3].name.lower()))
    return items


def run_library_move(
    repo: JobRepository,
    store: LibraryStore,
    jobs: list[Job] | None = None,
    *,
    extra_paths: list[Path] | None = None,
    cancel: threading.Event | None = None,
    on_progress: Callable[[MoveProgress], None] | None = None,
    between_files: Callable[[Any], None] | None = None,
    download_roots: list[Path] | None = None,
    chunk_size: int | None = None,
) -> MoveReport:
    """Move completed downloads and loose download-tree videos into the library.

    Checks *cancel* before each file and during chunked cross-drive copy.
    UI callers must run this off the Flet thread.
    """
    if store.root() is None:
        raise RuntimeError("Library root is not set")
    log_file = _new_move_log()
    dropped = purge_missing_library_items(store)
    _log_line(log_file, f"start library_root={store.root()} purged_missing={dropped}")
    roots = list(download_roots or [])
    if roots:
        healed = heal_job_download_paths(repo, download_roots=roots, library_root=store.root())
        if healed:
            _log_line(log_file, f"healed_job_paths={healed}")
    batch_jobs = jobs if jobs is not None else completed_jobs_not_in_library(repo, store)
    work = build_move_work(batch_jobs, extra_paths)
    job_count = sum(1 for row in work if row[0] is not None)
    disk_count = sum(1 for row in work if row[0] is None)
    report = MoveReport(disk_found=disk_count, log_path=str(log_file) if log_file else None)
    _log_line(log_file, f"batch jobs={job_count} disk={disk_count} unique={len(work)}")
    total = len(work)

    def _emit(progress: MoveProgress) -> None:
        if not on_progress:
            return
        try:
            on_progress(progress)
        except Exception:  # noqa: BLE001 — UI ticks must not abort the batch
            log.exception("Library move progress callback failed at %s/%s", progress.index, progress.total)

    try:
        for i, (job, extras, path, src, size) in enumerate(work, 1):
            if cancel is not None and cancel.is_set():
                report.cancelled = True
                report.skipped += total - i + 1
                break
            label = _copy_label(_label_for(job, path or src), size)
            ident = f"#{job.id}" if job is not None else "disk"
            _emit(
                MoveProgress(
                    index=i,
                    total=total,
                    current_name=label,
                    moved=report.moved,
                    failed=report.failed,
                    skipped=report.skipped,
                    bytes_total=size,
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

            def _on_bytes(copied: int, total_bytes: int, *, _i=i, _label=label) -> None:
                _emit(
                    MoveProgress(
                        index=_i,
                        total=total,
                        current_name=_label,
                        moved=report.moved,
                        failed=report.failed,
                        skipped=report.skipped,
                        bytes_copied=copied,
                        bytes_total=total_bytes,
                        copying=True,
                    )
                )

            xfer = {
                "cancel": cancel,
                "on_copy_progress": _on_bytes,
                "log_line": lambda m, _log=log_file: _log_line(_log, m),
                "file_index": i,
            }
            if chunk_size is not None:
                xfer["chunk_size"] = chunk_size
            try:
                if job is not None:
                    result = move_into_library(repo, store, job, **xfer)
                    for extra in extras:
                        _update_job_paths(repo, extra, src, result.dest_path)
                else:
                    assert path is not None
                    result = move_path_into_library(store, path, **xfer)
                report.results.append(result)
                report.moved += 1
                _log_line(
                    log_file,
                    f"OK {ident} src={result.source_path} dst={result.dest_path}",
                )
            except TransferCancelled:
                report.cancelled = True
                report.skipped += total - i + 1
                _log_line(log_file, f"ABORT in-copy {ident} src={src}")
                break
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
        self.download_roots: list[Path] = []
        self.chunk_size: int | None = None

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
        download_roots: list[Path] | None = None,
        on_progress: Callable[[MoveProgress], None] | None = None,
        on_done: Callable[[MoveReport], None] | None = None,
        chunk_size: int | None = None,
    ) -> None:
        if self.running:
            raise RuntimeError("A library move is already running")
        self.cancel.clear()
        self.report = None
        self.job_ids = list(job_ids)
        self.extra_paths = [Path(p) for p in extra_paths or []]
        self.download_roots = [Path(p) for p in download_roots or []]
        self.chunk_size = chunk_size

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
                    download_roots=self.download_roots,
                    chunk_size=self.chunk_size,
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
