"""Sequential single-job worker over SQLite queue."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from frameforge.db.repository import Job, JobRepository


JobHandler = Callable[[Job, JobRepository], None]


@dataclass
class WorkerEvent:
    job_id: int
    stage: str
    at: float


@dataclass
class SequentialWorker:
    """Processes at most one job at a time from a JobRepository."""

    repo: JobRepository
    download_handler: JobHandler
    upscale_handler: JobHandler | None = None
    poll_interval: float = 0.05
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    events: list[WorkerEvent] = field(default_factory=list)

    def recover(self) -> list[int]:
        return self.repo.recover_interrupted()

    def start(self, *, daemon: bool = True) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.recover()
        self._thread = threading.Thread(target=self._loop, name="frameforge-worker", daemon=daemon)
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def run_until_idle(self, timeout: float = 120.0) -> None:
        """Process pending jobs in this thread until queue idle or timeout."""
        self.recover()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._process_one():
                pending = self.repo.count_by_status("pending")
                busy = self.repo.count_by_status("downloading") + self.repo.count_by_status(
                    "upscaling"
                )
                if pending == 0 and busy == 0:
                    return
            time.sleep(self.poll_interval)
        raise TimeoutError("Worker timed out before becoming idle")

    def _loop(self) -> None:
        while not self._stop.is_set():
            worked = self._process_one()
            if not worked:
                time.sleep(self.poll_interval)

    def _process_one(self) -> bool:
        # Prefer continuing a job that finished download and needs upscale
        for job in self.repo.list_jobs("download_completed"):
            if job.upscale:
                return self._run_upscale(job)
            self.repo.update_status(job.id, "completed", progress=100.0)
            return True

        job = self.repo.claim_next_pending()
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
