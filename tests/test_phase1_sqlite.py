"""Phase 1.1 — SQLite schema, migrations, repository (real on-disk DB)."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.connection import connect
from frameforge.db.migrate import current_version, migrate
from frameforge.db.repository import JobRepository


def test_wal_mode_and_migrate(tmp_path: Path):
    db = tmp_path / "frameforge.db"
    conn = connect(db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"
    assert migrate(conn) >= 1
    assert current_version(conn) >= 1
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "jobs" in tables
    assert "download_archive" in tables
    assert "schema_migrations" in tables
    conn.close()


def test_enqueue_list_priority_and_claim(tmp_path: Path):
    db = tmp_path / "frameforge.db"
    repo = JobRepository(db)
    low = repo.enqueue("https://example.com/a", title="a", priority=1)
    high = repo.enqueue("https://example.com/b", title="b", priority=10)
    mid = repo.enqueue("https://example.com/c", title="c", priority=5)
    assert repo.list_jobs("pending")[0].id == high.id

    claimed = repo.claim_next_pending()
    assert claimed is not None
    assert claimed.id == high.id
    assert claimed.status == "downloading"
    assert repo.count_by_status("downloading") == 1

    # Sequential invariant: cannot claim another while downloading
    second = repo.claim_next_pending()
    assert second is None
    assert repo.count_by_status("downloading") == 1

    repo.update_status(claimed.id, "completed", progress=100)
    claimed2 = repo.claim_next_pending()
    assert claimed2 is not None
    assert claimed2.id == mid.id
    repo.close()


def test_persistence_across_reopen(tmp_path: Path):
    db = tmp_path / "persist.db"
    repo = JobRepository(db)
    job = repo.enqueue("https://example.com/persist", title="persist", priority=3)
    job_id = job.id
    repo.close()

    repo2 = JobRepository(db)
    loaded = repo2.get(job_id)
    assert loaded.url == "https://example.com/persist"
    assert loaded.title == "persist"
    assert loaded.priority == 3
    assert loaded.status == "pending"
    repo2.close()
    assert db.exists()
    assert db.stat().st_size > 0


def test_recover_interrupted(tmp_path: Path):
    db = tmp_path / "recover.db"
    repo = JobRepository(db)
    job = repo.enqueue("https://example.com/x")
    repo.claim_next_pending()
    assert repo.get(job.id).status == "downloading"
    recovered = repo.recover_interrupted()
    assert job.id in recovered
    assert repo.get(job.id).status == "pending"
    repo.close()
