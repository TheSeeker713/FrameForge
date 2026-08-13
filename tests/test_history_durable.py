"""Step 2.1 — history survives queue clear and process restart."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository


def test_clear_from_queue_still_listed_in_history(tmp_path: Path):
    db = tmp_path / "h.db"
    repo = JobRepository(db)
    done = repo.enqueue("https://example.com/ok", title="Done")
    failed = repo.enqueue("https://example.com/bad", title="Fail")
    pending = repo.enqueue("https://example.com/p", title="Later")
    repo.update_status(done.id, "completed", progress=100)
    repo.update_status(failed.id, "failed", error="bot")
    repo.clear_finished_from_queue()
    hist = {j.id: j.status for j in repo.list_history()}
    assert hist[done.id] == "completed"
    assert hist[failed.id] == "failed"
    assert pending.id not in hist
    assert pending.id in {j.id for j in repo.list_jobs()}
    repo.close()

    repo2 = JobRepository(db)
    hist2 = {j.id: j.status for j in repo2.list_history()}
    assert hist2[done.id] == "completed"
    assert hist2[failed.id] == "failed"
    assert repo2.get(done.id).queue_hidden is True
    assert {j.id for j in repo2.list_jobs()} == {pending.id}
    repo2.close()
