"""Sequential single-job worker over SQLite queue."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from frameforge.db.repository import Job, JobRepository


JobHandler = Callable[[Job, JobRepository], None]


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
    poll_interval: float = 0.05
    _stop: threading.Event = field(default_factory=threading.Event)
    _armed: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _only_ids: set[int] | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    events: list[WorkerEvent] = field(default_factory=list)

    def recover(self) -> list[int]:
        return self.repo.recover_interrupted()

    @property
    def is_armed(self) -> bool:
        return self._armed.is_set()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, *, daemon: bool = True, armed: bool = False) -> None:
        """Start the background loop. Does not claim jobs unless armed=True."""
        if self._thread and self._thread.is_alive():
            if armed:
                self._armed.set()
            return
        self._stop.clear()
        if armed:
            self._armed.set()
        else:
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

    def request_download_all(self) -> None:
        """Arm worker to process all pending jobs sequentially until drained."""
        with self._lock:
            self._only_ids = None
            self._armed.set()
        self.recover()
        self.start(armed=True)

    def request_download_ids(self, job_ids: Iterable[int]) -> None:
        """Arm worker to process only the given pending job IDs."""
        ids = {int(i) for i in job_ids}
        with self._lock:
            self._only_ids = ids
            self._armed.set()
        self.recover()
        self.start(armed=True)

    def request_upscale_ids(self, job_ids: Iterable[int]) -> list[int]:
        """Queue completed jobs for 2× upscale and arm the worker (no new downloads).

        Returns the list of job IDs successfully queued. Raises ValueError if none
        are eligible (caller may catch and show a message).
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
            self._armed.set()
        self.start(armed=True)
        return queued

    def run_until_idle(self, timeout: float = 120.0) -> None:
        """Process pending jobs in this thread until queue idle or timeout.

        Used by tests; arms for all pending for the duration of the call.
        """
        self.recover()
        with self._lock:
            self._only_ids = None
            self._armed.set()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._process_one():
                pending = self.repo.count_by_status("pending")
                busy = self.repo.count_by_status("downloading") + self.repo.count_by_status(
                    "upscaling"
                )
                download_completed = self.repo.count_by_status("download_completed")
                if pending == 0 and busy == 0 and download_completed == 0:
                    self.disarm()
                    return
            time.sleep(self.poll_interval)
        self.disarm()
        raise TimeoutError("Worker timed out before becoming idle")

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._armed.is_set():
                time.sleep(self.poll_interval)
                continue
            worked = self._process_one()
            if not worked:
                # Disarm when no eligible pending and nothing busy / chained
                pending = self._eligible_pending_count()
                busy = self.repo.count_by_status("downloading") + self.repo.count_by_status(
                    "upscaling"
                )
                chained = self.repo.count_by_status("download_completed")
                if pending == 0 and busy == 0 and chained == 0:
                    self.disarm()
                time.sleep(self.poll_interval)

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
        if not self._armed.is_set():
            return False

        # Prefer continuing a job that finished download and needs upscale
        for job in self.repo.list_jobs("download_completed"):
            if job.upscale:
                return self._run_upscale(job)
            self.repo.update_status(job.id, "completed", progress=100.0)
            return True

        job = self.repo.claim_next_pending(self._claim_filter())
        if not job:
            return False
        return self._run_download(job)

    def _run_download(self, job: Job) -> bool:
        self.events.append(WorkerEvent(job.id, "download_start", time.time()))
        try:
            self.download_handler(job, self.repo)
            job = self.repo.get(job.id)
            if job.status == "cancelled":
                return True
            if job.upscale:
                self.repo.update_status(job.id, "download_completed", progress=100.0)
            else:
                self.repo.update_status(job.id, "completed", progress=100.0)
            self.events.append(WorkerEvent(job.id, "download_end", time.time()))
            return True
        except Exception as exc:  # noqa: BLE001
            self.repo.update_status(job.id, "failed", error=str(exc))
            self.events.append(WorkerEvent(job.id, "download_fail", time.time()))
            return True

    def _run_upscale(self, job: Job) -> bool:
        self.repo.update_status(job.id, "upscaling", progress=0)
        self.events.append(WorkerEvent(job.id, "upscale_start", time.time()))
        try:
            if not self.upscale_handler:
                raise RuntimeError("Upscale requested but no upscale_handler configured")
            self.upscale_handler(job, self.repo)
            job = self.repo.get(job.id)
            if job.status != "cancelled":
                self.repo.update_status(job.id, "completed", progress=100.0)
            self.events.append(WorkerEvent(job.id, "upscale_end", time.time()))
            return True
        except Exception as exc:  # noqa: BLE001
            self.repo.update_status(job.id, "failed", error=str(exc))
            self.events.append(WorkerEvent(job.id, "upscale_fail", time.time()))
            return True
