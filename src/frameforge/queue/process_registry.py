"""Track the active job subprocess so cancel can kill the process tree."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from frameforge.util.process_tree import kill_process_tree, pid_is_running


@dataclass
class ProcessRegistry:
    """At most one active killable PID per job (sequential worker)."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _job_pid: dict[int, int] = field(default_factory=dict)
    _killed_jobs: set[int] = field(default_factory=set)
    _paused_jobs: set[int] = field(default_factory=set)

    def register(self, job_id: int, pid: int) -> None:
        with self._lock:
            self._job_pid[int(job_id)] = int(pid)
            self._killed_jobs.discard(int(job_id))
            self._paused_jobs.discard(int(job_id))

    def unregister(self, job_id: int) -> None:
        with self._lock:
            self._job_pid.pop(int(job_id), None)

    def pid_for(self, job_id: int) -> int | None:
        with self._lock:
            return self._job_pid.get(int(job_id))

    def was_killed(self, job_id: int) -> bool:
        with self._lock:
            return int(job_id) in self._killed_jobs

    def mark_paused(self, job_id: int) -> None:
        with self._lock:
            self._paused_jobs.add(int(job_id))

    def was_paused(self, job_id: int) -> bool:
        with self._lock:
            return int(job_id) in self._paused_jobs

    def kill(self, job_id: int) -> bool:
        """Kill process tree for job if registered. Returns True if a kill was attempted."""
        with self._lock:
            pid = self._job_pid.get(int(job_id))
            if pid is None:
                return False
            self._killed_jobs.add(int(job_id))
        kill_process_tree(pid)
        return True

    def active_pids(self) -> dict[int, int]:
        with self._lock:
            return dict(self._job_pid)

    def ensure_dead(self, job_id: int, timeout: float = 10.0) -> bool:
        """After kill, wait until the registered PID is gone (or already unregistered)."""
        pid = self.pid_for(job_id)
        if pid is None:
            return True
        deadline_slices = max(1, int(timeout / 0.05))
        for _ in range(deadline_slices):
            if not pid_is_running(pid):
                self.unregister(job_id)
                return True
            import time

            time.sleep(0.05)
        gone = not pid_is_running(pid)
        if gone:
            self.unregister(job_id)
        return gone
