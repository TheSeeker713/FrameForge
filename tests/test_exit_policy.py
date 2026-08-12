"""Step 2.1 — central exit policy helper."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.gui.exit_policy import (
    CHOICE_WAIT_THEN_QUIT,
    NEEDS_CHOICE,
    QUIT_NOW,
    WAIT_IN_PROGRESS,
    apply_quit_choice,
    classify_exit,
    list_active_work,
)
from frameforge.queue.worker import SequentialWorker


def test_idle_queue_exits_without_choice(tmp_path: Path):
    repo = JobRepository(tmp_path / "idle.db")
    repo.enqueue("https://example.com/p")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    assert list_active_work(repo) == []
    assert classify_exit(repo, worker) == QUIT_NOW
    repo.close()


def test_active_download_requires_explicit_choice(tmp_path: Path):
    repo = JobRepository(tmp_path / "act.db")
    job = repo.enqueue("https://example.com/d")
    claimed = repo.claim_next_pending()
    assert claimed is not None
    assert claimed.status == "downloading"
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    assert [j.id for j in list_active_work(repo)] == [job.id]
    assert classify_exit(repo, worker) == NEEDS_CHOICE
    repo.close()


def test_wait_to_quit_disarms_and_classifies(tmp_path: Path):
    repo = JobRepository(tmp_path / "w.db")
    job = repo.enqueue("https://example.com/d")
    repo.claim_next_pending()
    other = repo.enqueue("https://example.com/next")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    worker._armed.set()
    assert worker.is_armed

    outcome = apply_quit_choice(worker, CHOICE_WAIT_THEN_QUIT)
    assert outcome == "wait"
    assert worker.wait_to_quit is True
    assert worker.is_armed is False
    assert classify_exit(repo, worker) == WAIT_IN_PROGRESS
    assert repo.get(job.id).status == "downloading"
    assert repo.get(other.id).status == "pending"
    assert repo.claim_next_pending() is None  # still busy with active stage

    repo.update_status(job.id, "completed", progress=100)
    assert classify_exit(repo, worker) == QUIT_NOW
    assert repo.get(other.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()
