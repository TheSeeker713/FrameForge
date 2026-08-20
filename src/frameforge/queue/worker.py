"""Sequential single-job worker over SQLite queue."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from frameforge.db.connection import is_transient_sqlite
from frameforge.db.repository import Job, JobRepository
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused

log = logging.getLogger(__name__)


JobHandler = Callable[[Job, JobRepository], None]

MAX_WORKER_EVENTS = 200
SQLITE_REQUEUE_MAX = 3


@dataclass
class WorkerEvent:
    job_id: int
    stage: str
    at: float


@dataclass
class SequentialWorker:
    """Processes at most one job at a time from a JobRepository.

    Manual-start model: the loop thread may run, but downloads are only claimed
    while armed (request_download_all / request_download_ids). When no matching
    work remains, the worker disarms itself (idle).
    """

    repo: JobRepository
    download_handler: JobHandler
    upscale_handler: JobHandler | None = None
    convert_handler: JobHandler | None = None
    upscale_pipeline: object | None = None
    poll_interval: float = 0.05
    _stop: threading.Event = field(default_factory=threading.Event)
    _armed: threading.Event = field(default_factory=threading.Event)
    _wait_to_quit: threading.Event = field(default_factory=threading.Event)
    _fail_pause_halt: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _only_ids: set[int] | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    events: list[WorkerEvent] = field(default_factory=list)
    processes: ProcessRegistry = field(default_factory=ProcessRegistry)
    on_fail_pause: Callable[[Job], None] | None = field(default=None)
    _last_download_finished: float = field(default=0.0, init=False, repr=False)

    def recover(self) -> list[int]:
        return self.repo.recover_interrupted()

    def prepare_idle_launch(self) -> list[int]:
        """Reset crashed active stages to pending. Never arm or start the loop."""
        self.disarm()
        return self.recover()

    def cancel_job(self, job_id: int) -> Job:
        """Mark job cancelled and kill any active yt-dlp/aria2c/ffmpeg tree."""
        self.clear_wait_to_quit()
        job = self.repo.cancel(job_id)
        self.processes.kill(job_id)
        return job

    def kill_active_processes(self) -> None:
        """Hard-kill in-flight yt-dlp/aria2c/ffmpeg trees and disarm. Does not join."""
        self.disarm()
        self.clear_wait_to_quit()
        self.processes.kill_all()

    def pause_job(self, job_id: int) -> Job:
        """Hard-stop the active process tree, mark paused, keep partials, go idle."""
        from frameforge.download.partials import collect_partial_artifacts

        self.disarm()
        job = self.repo.get(job_id)
        if job.status == "paused":
            return job
        self.processes.mark_paused(job_id)
        paused = self.repo.pause(job_id)
        self.processes.terminate(job_id)
        opts = paused.options()
        out_dir = opts.get("download_output_dir")
        if out_dir:
            from frameforge.paths import temp_dir

            extra = [temp_dir() / "dl"]
            from pathlib import Path

            nested = Path(out_dir) / ".ff-temp"
            extra.append(nested)
            parts = collect_partial_artifacts(out_dir, extra_dirs=extra)
            self.repo.merge_options(
                job_id,
                {"partial_paths": parts, "download_output_dir": str(out_dir)},
            )
            part_files = [p for p in parts if str(p).lower().endswith(".part")]
            if part_files and not paused.download_path:
                self.repo.set_paths(job_id, download_path=part_files[0])
        return self.repo.get(job_id)

    def resume_job(self, job_id: int) -> Job:
        """Resume a paused job with continue semantics. Sequential: one active stage."""
        self.processes.clear_signals(job_id)
        job = self.repo.resume_paused(job_id)
        if job.status == "download_completed":
            with self._lock:
                self._only_ids = set()
                self._fail_pause_halt.clear()
                self._armed.set()
            self.start(armed=True)
            return job
        if job.status == "convert_pending":
            with self._lock:
                self._only_ids = set()
                self._fail_pause_halt.clear()
                self._armed.set()
            self.start(armed=True)
            return job
        self.request_download_ids([job.id])
        return self.repo.get(job.id)

    @property
    def is_armed(self) -> bool:
        return self._armed.is_set()

    @property
    def is_fail_paused(self) -> bool:
        return self._fail_pause_halt.is_set()

    def halt_after_fail(self) -> None:
        """Disarm and refuse further claims until the user explicitly resumes."""
        with self._lock:
            self._armed.clear()
            self._only_ids = None
            self._fail_pause_halt.set()

    def clear_fail_pause_halt(self) -> None:
        self._fail_pause_halt.clear()

    def _claims_allowed(self) -> bool:
        with self._lock:
            return self._armed.is_set() and not self._fail_pause_halt.is_set()

    def stop_run(self) -> None:
        """Cancel the in-flight stage, disarm, leave remaining jobs pending."""
        self.clear_wait_to_quit()
        self.disarm()
        self.clear_fail_pause_halt()
        for status in ("downloading", "upscaling", "converting"):
            for job in list(self.repo.list_jobs(status)):
                self.cancel_job(job.id)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, *, daemon: bool = True, armed: bool = False) -> None:
        """Start the background loop. Does not claim jobs unless armed=True."""
        if armed:
            with self._lock:
                self._fail_pause_halt.clear()
                self._armed.set()
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        if not armed:
            self._armed.clear()
        self._thread = threading.Thread(target=self._loop, name="frameforge-worker", daemon=daemon)
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._armed.clear()
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def disarm(self) -> None:
        """Stop claiming new pending downloads (idle). In-flight job may finish."""
        with self._lock:
            self._armed.clear()
            self._only_ids = None

    def begin_wait_to_quit(self) -> None:
        """Disarm further claims; let the current stage finish, then the UI may exit."""
        self._wait_to_quit.set()
        self.disarm()

    def clear_wait_to_quit(self) -> None:
        self._wait_to_quit.clear()

    @property
    def wait_to_quit(self) -> bool:
        return self._wait_to_quit.is_set()

    def request_download_all(self) -> None:
        """Arm worker to process all pending jobs sequentially until drained."""
        with self._lock:
            self._only_ids = None
            self._fail_pause_halt.clear()
            self._armed.set()
        self.recover()
        self.start(armed=True)

    def request_download_ids(self, job_ids: Iterable[int]) -> None:
        """Arm worker to process only the given pending job IDs."""
        ids = {int(i) for i in job_ids}
        for jid in ids:
            self.processes.clear_signals(jid)
        with self._lock:
            self._only_ids = ids
            self._fail_pause_halt.clear()
            self._armed.set()
        self.recover()
        self.start(armed=True)

    def request_upscale_ids(self, job_ids: Iterable[int], *, start_loop: bool = True) -> list[int]:
        """Queue completed jobs for 2× upscale and arm the worker (no new downloads).

        Returns the list of job IDs successfully queued. Raises ValueError if none
        are eligible (caller may catch and show a message).

        *start_loop* defaults True for the GUI. Tests that call ``_process_one`` on
        the main thread must pass ``start_loop=False`` so ONNX never runs on two
        threads in the same process (DirectML is not safe that way).
        """
        queued: list[int] = []
        errors: list[str] = []
        for jid in job_ids:
            try:
                self.repo.queue_for_upscale(int(jid))
                queued.append(int(jid))
            except ValueError as exc:
                errors.append(str(exc))
        if not queued:
            raise ValueError(
                "; ".join(errors) if errors else "No eligible completed jobs to upscale"
            )
        with self._lock:
            # Empty set: do not claim pending downloads; only process upscale stage
            self._only_ids = set()
            self._fail_pause_halt.clear()
            self._armed.set()
        if start_loop:
            self.start(armed=True)
        return queued

    def request_convert_ids(self, job_ids: Iterable[int], *, start_loop: bool = True) -> list[int]:
        """Queue completed jobs for MP3 convert and arm the worker (no new downloads)."""
        queued: list[int] = []
        errors: list[str] = []
        for jid in job_ids:
            try:
                self.repo.queue_for_convert(int(jid))
                queued.append(int(jid))
            except ValueError as exc:
                errors.append(str(exc))
        if not queued:
            raise ValueError(
                "; ".join(errors) if errors else "No eligible completed jobs to convert"
            )
        with self._lock:
            self._only_ids = set()
            self._fail_pause_halt.clear()
            self._armed.set()
        if start_loop:
            self.start(armed=True)
        return queued

    def run_until_idle(self, timeout: float = 120.0) -> None:
        """Process pending jobs in this thread until queue idle or timeout.

        Used by tests; arms for all pending for the duration of the call.
        """
        self.recover()
        with self._lock:
            self._only_ids = None
            self._fail_pause_halt.clear()
            self._armed.set()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._process_one():
                if not self.is_armed:
                    return
                pending = self.repo.count_by_status("pending")
                busy = (
                    self.repo.count_by_status("downloading")
                    + self.repo.count_by_status("upscaling")
                    + self.repo.count_by_status("converting")
                )
                download_completed = self.repo.count_by_status("download_completed")
                convert_pending = self.repo.count_by_status("convert_pending")
                if pending == 0 and busy == 0 and download_completed == 0 and convert_pending == 0:
                    self.disarm()
                    return
            time.sleep(self.poll_interval)
        self.disarm()
        raise TimeoutError("Worker timed out before becoming idle")

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._claims_allowed():
                time.sleep(self.poll_interval)
                continue
            try:
                worked = self._process_one()
                if not worked:
                    # Disarm when no eligible pending and nothing busy / chained
                    pending = self._eligible_pending_count()
                    busy = (
                        self.repo.count_by_status("downloading")
                        + self.repo.count_by_status("upscaling")
                        + self.repo.count_by_status("converting")
                    )
                    chained = self.repo.count_by_status("download_completed")
                    convert_pending = self.repo.count_by_status("convert_pending")
                    if pending == 0 and busy == 0 and chained == 0 and convert_pending == 0:
                        self.disarm()
                    time.sleep(self.poll_interval)
            except Exception as exc:  # noqa: BLE001
                # Never kill the background loop. Transient sqlite must not cascade
                # into failing a recoverable in-flight job.
                log.exception("worker loop recovered from internal error")
                if isinstance(exc, sqlite3.OperationalError) or is_transient_sqlite(exc):
                    time.sleep(max(self.poll_interval, 0.05))
                    continue
                self._fail_stuck_active_stages(f"Worker recovered from internal error: {exc}")
                time.sleep(self.poll_interval)

    def _fail_stuck_active_stages(self, reason: str) -> None:
        from frameforge.errors import annotate_job_error

        if is_transient_sqlite(reason):
            return
        for status in ("downloading", "upscaling", "converting"):
            for job in list(self.repo.list_jobs(status)):
                annotate_job_error(self.repo, job.id, reason, url=job.url)
                self._maybe_fail_pause(job.id)

    def _is_sqlite_infra(self, exc: BaseException) -> bool:
        return isinstance(exc, sqlite3.OperationalError) or is_transient_sqlite(exc)

    def _handle_sqlite_infra(self, job_id: int, exc: BaseException, *, stage: str) -> bool:
        """Requeue a recoverable job on transient sqlite. True if handled.

        After SQLITE_REQUEUE_MAX attempts, persist category db_error (not yt-dlp unknown).
        """
        if not self._is_sqlite_infra(exc):
            return False
        from frameforge.errors import annotate_job_error

        try:
            job = self.repo.get(job_id)
            n = int(job.options().get("db_retry_count") or 0) + 1
            msg = f"sqlite3.{type(exc).__name__}: {exc}"
            recoverable = job.status in (
                "downloading",
                "upscaling",
                "converting",
                "pending",
                "download_completed",
                "convert_pending",
            )
            if n <= SQLITE_REQUEUE_MAX and recoverable:
                self.repo.merge_options(job_id, {"db_retry_count": n})
                if job.status == "downloading":
                    self.repo.update_status(job_id, "pending", error=None)
                elif job.status == "upscaling":
                    self.repo.update_status(job_id, "download_completed", error=None)
                elif job.status == "converting":
                    self.repo.update_status(job_id, "convert_pending", error=None)
                self._record_event(job_id, f"{stage}_db_retry")
                return True
            annotate_job_error(self.repo, job_id, msg, url=job.url)
            self._record_event(job_id, f"{stage}_fail")
            self._maybe_fail_pause(job_id)
            return True
        except sqlite3.OperationalError:
            return True

    def _eligible_pending_count(self) -> int:
        with self._lock:
            only = None if self._only_ids is None else set(self._only_ids)
        if only is None:
            return self.repo.count_by_status("pending")
        return sum(1 for j in self.repo.list_jobs("pending") if j.id in only)

    def _claim_filter(self) -> list[int] | None:
        with self._lock:
            if self._only_ids is None:
                return None
            return list(self._only_ids)

    def _process_one(self) -> bool:
        if not self._claims_allowed():
            return False

        claimed_convert = self.repo.claim_next_convert()
        if claimed_convert:
            return self._run_convert(claimed_convert)

        # Prefer continuing a job that finished download and needs upscale
        for job in self.repo.list_jobs("download_completed"):
            if job.upscale:
                return self._run_upscale(job)
            self.repo.update_status(job.id, "completed", progress=100.0)
            return True

        if self._eligible_pending_count() == 0:
            return False
        if not self._wait_inter_job_delay():
            return False
        job = self.repo.claim_next_pending(self._claim_filter())
        if not job:
            return False
        return self._run_download(job)

    def _wait_inter_job_delay(self) -> bool:
        """Sleep between download jobs. First claim of a run is immediate.

        Returns False when stop/disarm/halt interrupts the wait (do not claim).
        """
        from frameforge.download.throughput import inter_job_delay_sec

        delay = inter_job_delay_sec(self.repo)
        started = self._last_download_finished
        if delay <= 0 or started <= 0:
            return self._claims_allowed()
        deadline = started + delay
        while time.time() < deadline:
            if self._stop.is_set() or not self._claims_allowed():
                return False
            time.sleep(min(0.1, max(0.0, deadline - time.time())))
        return self._claims_allowed()

    def _preserve_paused(self, job_id: int, exc: BaseException) -> bool:
        """If job was paused (or pause exception), keep paused — never failed/cancelled.

        If the user already resumed (status is pending / download_completed), do not
        re-apply paused — just swallow the in-flight pause exception.
        """
        current = self.repo.get(job_id)
        if current.status == "paused":
            return True
        if not isinstance(exc, DownloadPaused):
            return False
        if current.status in ("pending", "download_completed", "completed", "convert_pending"):
            return True
        if current.status in ("downloading", "upscaling", "converting"):
            try:
                self.repo.pause(job_id)
            except ValueError:
                pass
            return True
        return True

    def _preserve_cancelled(self, job_id: int, exc: BaseException) -> bool:
        """Keep user-cancelled jobs cancelled. Typed DownloadCancelled only — never English."""
        current = self.repo.get(job_id)
        if current.status == "paused" or isinstance(exc, DownloadPaused):
            return False
        if current.status == "cancelled" or isinstance(exc, DownloadCancelled):
            if current.status != "cancelled":
                self.repo.cancel(job_id)
            return True
        return False

    def _record_event(self, job_id: int, stage: str) -> None:
        self.events.append(WorkerEvent(job_id, stage, time.time()))
        overflow = len(self.events) - MAX_WORKER_EVENTS
        if overflow > 0:
            del self.events[:overflow]

    def _maybe_fail_pause(self, job_id: int) -> None:
        from frameforge.queue.fail_pause import maybe_fail_pause

        job = self.repo.get(job_id)
        if maybe_fail_pause(self, self.repo, job) and self.on_fail_pause is not None:
            try:
                self.on_fail_pause(job)
            except Exception:  # noqa: BLE001
                pass

    def _run_download(self, job: Job) -> bool:
        self._record_event(job.id, "download_start")
        try:
            self.download_handler(job, self.repo)
            job = self.repo.get(job.id)
            if job.status in ("cancelled", "paused", "pending"):
                return True
            if job.status == "failed":
                self._record_event(job.id, "download_fail")
                self._maybe_fail_pause(job.id)
                return True
            if job.upscale:
                self.repo.update_status(job.id, "download_completed", progress=100.0)
            else:
                self.repo.update_status(job.id, "completed", progress=100.0)
            self._record_event(job.id, "download_end")
            return True
        except Exception as exc:  # noqa: BLE001
            if self._handle_sqlite_infra(job.id, exc, stage="download"):
                return True
            if self._preserve_paused(job.id, exc):
                self._record_event(job.id, "download_pause")
                return True
            if self._preserve_cancelled(job.id, exc):
                self.repo.merge_options(job.id, {"error_category": "cancelled", "auth_required": False})
                self._record_event(job.id, "download_cancel")
                return True
            from frameforge.errors import annotate_job_error

            annotate_job_error(self.repo, job.id, str(exc), url=job.url)
            self._record_event(job.id, "download_fail")
            self._maybe_fail_pause(job.id)
            return True
        finally:
            self._last_download_finished = time.time()
            self.processes.unregister(job.id)

    def _run_upscale(self, job: Job) -> bool:
        self.repo.update_status(job.id, "upscaling", progress=0)
        self._record_event(job.id, "upscale_start")
        try:
            if not self.upscale_handler:
                raise RuntimeError("Upscale requested but no upscale_handler configured")
            self.upscale_handler(job, self.repo)
            job = self.repo.get(job.id)
            if job.status == "failed":
                self._record_event(job.id, "upscale_fail")
                self._maybe_fail_pause(job.id)
                return True
            if job.status not in ("cancelled", "paused"):
                self.repo.update_status(job.id, "completed", progress=100.0)
            self._record_event(job.id, "upscale_end")
            return True
        except Exception as exc:  # noqa: BLE001
            if self._handle_sqlite_infra(job.id, exc, stage="upscale"):
                return True
            if self._preserve_paused(job.id, exc):
                self._record_event(job.id, "upscale_pause")
                return True
            if self._preserve_cancelled(job.id, exc):
                self.repo.merge_options(job.id, {"error_category": "cancelled", "auth_required": False})
                self._record_event(job.id, "upscale_cancel")
                return True
            from frameforge.errors import annotate_job_error, option_patch_from_exc

            annotate_job_error(self.repo, job.id, str(exc), url=job.url, extra=option_patch_from_exc(exc))
            self._record_event(job.id, "upscale_fail")
            self._maybe_fail_pause(job.id)
            return True
        finally:
            self.processes.unregister(job.id)

    def _run_convert(self, job: Job) -> bool:
        self._record_event(job.id, "convert_start")
        try:
            if not self.convert_handler:
                raise RuntimeError("Convert requested but no convert_handler configured")
            self.convert_handler(job, self.repo)
            job = self.repo.get(job.id)
            if job.status == "failed":
                self._record_event(job.id, "convert_fail")
                self._maybe_fail_pause(job.id)
                return True
            if job.status not in ("cancelled", "paused"):
                self.repo.update_status(job.id, "completed", progress=100.0)
            self._record_event(job.id, "convert_end")
            return True
        except Exception as exc:  # noqa: BLE001
            if self._handle_sqlite_infra(job.id, exc, stage="convert"):
                return True
            if self._preserve_paused(job.id, exc):
                self._record_event(job.id, "convert_pause")
                return True
            if self._preserve_cancelled(job.id, exc):
                self.repo.merge_options(job.id, {"error_category": "cancelled", "auth_required": False})
                self._record_event(job.id, "convert_cancel")
                return True
            from frameforge.errors import annotate_job_error

            annotate_job_error(self.repo, job.id, str(exc), url=job.url)
            self._record_event(job.id, "convert_fail")
            self._maybe_fail_pause(job.id)
            return True
        finally:
            self.processes.unregister(job.id)
