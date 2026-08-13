"""Step 2.3 — history re-download (new pending) and clear selected/all."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker


def test_reenqueue_creates_new_pending_keeps_history(tmp_path: Path):
    repo = JobRepository(tmp_path / "r.db")
    done = repo.enqueue("https://example.com/a", title="A")
    repo.update_status(done.id, "completed", progress=100)
    new_ids = repo.reenqueue_as_pending([done.id])
    assert len(new_ids) == 1
    created = repo.get(new_ids[0])
    assert created.id != done.id
    assert created.status == "pending"
    assert created.url == done.url
    assert repo.get(done.id).status == "completed"
    assert done.id in {j.id for j in repo.list_history()}
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    assert worker.is_armed is False
    repo.close()


def test_clear_history_selected_and_all(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    a = repo.enqueue("https://example.com/a")
    b = repo.enqueue("https://example.com/b")
    c = repo.enqueue("https://example.com/c")
    repo.update_status(a.id, "completed", progress=100)
    repo.update_status(b.id, "failed", error="x")
    repo.update_status(c.id, "cancelled")
    assert repo.clear_history([a.id]) == 1
    hist = {j.id for j in repo.list_history()}
    assert a.id not in hist
    assert b.id in hist
    n = repo.clear_history(all_rows=True)
    assert n == 2
    assert repo.list_history() == []
    assert repo.get(a.id).status == "completed"
    repo.close()
