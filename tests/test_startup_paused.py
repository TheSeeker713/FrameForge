"""Step 2.3 — paused jobs stay paused on startup; crashed actives still recover."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker


def test_paused_not_recovered_or_auto_claimed(tmp_path: Path):
    db = tmp_path / "p.db"
    repo = JobRepository(db)
    paused = repo.enqueue("https://example.com/paused")
    crashed = repo.enqueue("https://example.com/crashed")
    repo.claim_next_pending()
    repo.pause(paused.id)
    repo.claim_next_pending()
    assert repo.get(paused.id).status == "paused"
    assert repo.get(crashed.id).status == "downloading"
    repo.close()

    repo2 = JobRepository(db)
    worker = SequentialWorker(repo2, download_handler=lambda j, r: None)
    recovered = worker.recover()
    assert crashed.id in recovered
    assert paused.id not in recovered
    assert repo2.get(paused.id).status == "paused"
    assert repo2.get(crashed.id).status == "pending"

    worker.request_download_all()
    # recover already ran; paused must not become downloading
    assert repo2.get(paused.id).status == "paused"
    worker.disarm()
    worker.stop(timeout=2)
    repo2.close()


def test_recover_interrupted_skips_paused(tmp_path: Path):
    repo = JobRepository(tmp_path / "r.db")
    job = repo.enqueue("https://example.com/x")
    repo.claim_next_pending()
    repo.pause(job.id)
    assert repo.recover_interrupted() == []
    assert repo.get(job.id).status == "paused"
    claimed = repo.claim_next_pending()
    assert claimed is None
    repo.close()
