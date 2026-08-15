"""Inter-job cooldown: first claim is immediate; later pending waits Settings delay."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.throughput import inter_job_delay_sec
from frameforge.queue.worker import SequentialWorker


def test_default_inter_job_delay_is_three_seconds(tmp_path: Path):
    repo = JobRepository(tmp_path / "d.db")
    assert inter_job_delay_sec(repo) == 3.0
    repo.set_setting("inter_job_delay_sec", "0")
    assert inter_job_delay_sec(repo) == 0.0
    repo.set_setting("inter_job_delay_sec", "99")
    assert inter_job_delay_sec(repo) == 60.0
    repo.close()


def test_second_pending_waits_delay_first_does_not(tmp_path: Path):
    repo = JobRepository(tmp_path / "w.db")
    repo.set_setting("inter_job_delay_sec", "0.25")
    started: list[float] = []

    def handler(job, _repo):
        started.append(time.time())
        _repo.update_status(job.id, "completed", progress=100)

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    a = repo.enqueue("https://example.com/a")
    b = repo.enqueue("https://example.com/b")
    t0 = time.time()
    worker.run_until_idle(timeout=8)
    assert repo.get(a.id).status == "completed"
    assert repo.get(b.id).status == "completed"
    assert len(started) == 2
    assert started[0] - t0 < 0.2
    assert started[1] - started[0] >= 0.2
    worker.stop()
    repo.close()


def test_zero_delay_claims_next_immediately(tmp_path: Path):
    repo = JobRepository(tmp_path / "z.db")
    repo.set_setting("inter_job_delay_sec", "0")
    started: list[float] = []

    def handler(job, _repo):
        started.append(time.time())
        _repo.update_status(job.id, "completed", progress=100)

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    repo.enqueue("https://example.com/a")
    repo.enqueue("https://example.com/b")
    worker.run_until_idle(timeout=5)
    assert len(started) == 2
    assert started[1] - started[0] < 0.2
    worker.stop()
    repo.close()
