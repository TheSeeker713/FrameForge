"""Phase 1.2 — sequential worker + crash recovery."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.queue.worker import SequentialWorker


def _slow_handler(job: Job, repo: JobRepository) -> None:
    repo.update_progress(job.id, 10)
    time.sleep(0.15)
    repo.set_paths(job.id, download_path=f"C:/fake/{job.id}.mp4", output_path=f"C:/fake/{job.id}.mp4")
    repo.update_progress(job.id, 100)


def test_sequential_non_overlapping_execution(tmp_path: Path):
    db = tmp_path / "worker.db"
    repo = JobRepository(db)
    windows: list[tuple[int, float, float]] = []

    def handler(job: Job, r: JobRepository) -> None:
        start = time.time()
        time.sleep(0.12)
        end = time.time()
        windows.append((job.id, start, end))
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    repo.enqueue("https://example.com/1", priority=1)
    repo.enqueue("https://example.com/2", priority=2)
    repo.enqueue("https://example.com/3", priority=3)
    worker.run_until_idle(timeout=10)
    assert len(windows) == 3
    windows_sorted = sorted(windows, key=lambda w: w[1])
    for i in range(len(windows_sorted) - 1):
        _, _, end_i = windows_sorted[i]
        _, start_j, _ = windows_sorted[i + 1]
        assert end_i <= start_j + 1e-3, f"Overlapping downloads: {windows_sorted}"
    assert repo.count_by_status("downloading") == 0
    assert repo.count_by_status("completed") == 3
    # Never more than one downloading historically enforced by claim; final state clean
    repo.close()


def test_startup_recovery_then_complete(tmp_path: Path):
    db = tmp_path / "recover_worker.db"
    repo = JobRepository(db)
    job = repo.enqueue("https://example.com/recover")
    claimed = repo.claim_next_pending()
    assert claimed is not None
    assert claimed.status == "downloading"
    repo.close()

    # New process/repo simulates restart
    repo2 = JobRepository(db)
    worker = SequentialWorker(repo2, download_handler=_slow_handler, poll_interval=0.02)
    assert repo2.get(job.id).status == "downloading"
    recovered = worker.recover()
    assert job.id in recovered
    assert repo2.get(job.id).status == "pending"
    worker.run_until_idle(timeout=10)
    assert repo2.get(job.id).status == "completed"
    repo2.close()


def test_handler_failure_marks_failed(tmp_path: Path):
    db = tmp_path / "fail.db"
    repo = JobRepository(db)

    def boom(job: Job, r: JobRepository) -> None:
        raise RuntimeError("boom")

    worker = SequentialWorker(repo, download_handler=boom)
    job = repo.enqueue("https://example.com/fail")
    worker.run_until_idle(timeout=5)
    assert repo.get(job.id).status == "failed"
    assert "boom" in (repo.get(job.id).error or "")
    repo.close()
