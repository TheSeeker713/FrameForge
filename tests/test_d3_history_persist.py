"""D3 — history remains visible after reopening the on-disk SQLite DB."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository


def test_history_survives_repository_reopen(tmp_path: Path):
    db = tmp_path / "persist.db"
    repo = JobRepository(db)
    done = repo.enqueue("https://example.com/done", title="Keep me", extractor="generic")
    failed = repo.enqueue("https://example.com/fail", title="Also keep")
    pending = repo.enqueue("https://example.com/pend", title="not history")
    repo.update_status(done.id, "completed", progress=100)
    repo.update_status(failed.id, "failed", error="nope")
    done_id, failed_id, pending_id = done.id, failed.id, pending.id
    repo.close()

    repo2 = JobRepository(db)
    hist = repo2.list_history()
    ids = {j.id for j in hist}
    assert done_id in ids
    assert failed_id in ids
    assert pending_id not in ids
    titles = {j.id: j.title for j in hist}
    assert titles[done_id] == "Keep me"
    assert repo2.get(done_id).status == "completed"
    repo2.close()
