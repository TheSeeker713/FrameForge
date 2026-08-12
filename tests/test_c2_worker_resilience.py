"""C2 — worker loop survives handler exceptions; no stuck active stages."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.queue.worker import SequentialWorker


def test_injected_handler_exception_worker_stays_alive(tmp_path: Path):
    repo = JobRepository(tmp_path / "alive.db")
    seen: list[int] = []

    def handler(job: Job, r: JobRepository) -> None:
        seen.append(job.id)
        if "boom" in job.url:
            raise RuntimeError("injected handler failure")
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    boom = repo.enqueue("https://example.com/boom", priority=2)
    ok = repo.enqueue("https://example.com/ok", priority=1)
    worker.request_download_all()

    deadline = time.time() + 15
    while time.time() < deadline:
        st_b = repo.get(boom.id).status
        st_o = repo.get(ok.id).status
        if st_b in ("failed", "cancelled") and st_o in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)

    assert repo.get(boom.id).status == "failed"
    assert "injected" in (repo.get(boom.id).error or "")
    assert repo.get(ok.id).status == "completed"
    assert repo.count_by_status("downloading") == 0
    assert repo.count_by_status("upscaling") == 0
    assert worker.is_running is True
    worker.stop(timeout=5)
    repo.close()


def test_loop_internal_error_fails_stuck_active_and_continues(tmp_path: Path):
    repo = JobRepository(tmp_path / "stuck.db")
    calls = {"n": 0}

    def handler(job: Job, r: JobRepository) -> None:
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    orig = worker._process_one

    def boom_once() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("internal loop boom")
        return orig()

    worker._process_one = boom_once  # type: ignore[method-assign]
    job = repo.enqueue("https://example.com/after")
    worker.request_download_ids([job.id])
    deadline = time.time() + 15
    while time.time() < deadline:
        if repo.get(job.id).status == "completed":
            break
        time.sleep(0.05)
    assert repo.get(job.id).status == "completed", repo.get(job.id).error
    assert worker.is_running is True
    worker.stop(timeout=5)
    repo.close()


def test_startup_recovery_still_requeues_interrupted(tmp_path: Path):
    db = tmp_path / "rec.db"
    repo = JobRepository(db)
    job = repo.enqueue("https://example.com/mid")
    claimed = repo.claim_next_pending()
    assert claimed is not None
    assert claimed.status == "downloading"
    repo.close()

    repo2 = JobRepository(db)
    worker = SequentialWorker(repo2, download_handler=lambda j, r: None)
    recovered = worker.recover()
    assert job.id in recovered
    assert repo2.get(job.id).status == "pending"
    assert "Recovered after interrupted run" in (repo2.get(job.id).error or "")
    worker.stop(timeout=2)
    repo2.close()
