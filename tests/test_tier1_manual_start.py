"""Tier 1.1 — manual download control: no auto-start; explicit download actions."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.download.bulk_import import confirm_add, preview_import
from frameforge.queue.worker import SequentialWorker


def test_enqueue_stays_pending_while_worker_disarmed(tmp_path: Path):
    """Prove enqueue does not auto-download when worker is idle."""
    repo = JobRepository(tmp_path / "idle.db")
    job = repo.enqueue("https://example.com/a")
    started: list[int] = []

    def handler(job: Job, r: JobRepository) -> None:
        started.append(job.id)

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    worker.start(armed=False)
    time.sleep(0.2)
    assert repo.get(job.id).status == "pending"
    assert started == []
    assert worker.is_armed is False
    worker.stop()
    repo.close()


def test_import_leaves_pending_until_download_all(tmp_path: Path):
    repo = JobRepository(tmp_path / "import.db")
    f = tmp_path / "urls.txt"
    f.write_text("https://example.com/1\nhttps://example.com/2\n", encoding="utf-8")
    preview = preview_import(f, repo)
    ids = confirm_add(preview, repo)
    assert len(ids) == 2
    assert all(repo.get(i).status == "pending" for i in ids)

    started: list[int] = []

    def handler(job: Job, r: JobRepository) -> None:
        started.append(job.id)
        time.sleep(0.05)
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    worker.start(armed=False)
    time.sleep(0.15)
    assert started == []
    assert repo.count_by_status("pending") == 2

    worker.request_download_all()
    deadline = time.time() + 5
    while time.time() < deadline and repo.count_by_status("completed") < 2:
        time.sleep(0.05)
    worker.stop()
    assert sorted(started) == sorted(ids)
    assert repo.count_by_status("completed") == 2
    assert worker.is_armed is False
    repo.close()


def test_download_selected_only_those_ids(tmp_path: Path):
    repo = JobRepository(tmp_path / "sel.db")
    a = repo.enqueue("https://example.com/a", priority=1)
    b = repo.enqueue("https://example.com/b", priority=2)
    c = repo.enqueue("https://example.com/c", priority=3)
    done: list[int] = []

    def handler(job: Job, r: JobRepository) -> None:
        done.append(job.id)
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    worker.request_download_ids([a.id, c.id])
    deadline = time.time() + 5
    while time.time() < deadline and len(done) < 2:
        time.sleep(0.05)
    time.sleep(0.2)
    worker.stop()
    assert set(done) == {a.id, c.id}
    assert repo.get(b.id).status == "pending"
    assert repo.count_by_status("downloading") == 0
    repo.close()


def test_download_all_arms_then_idles(tmp_path: Path):
    repo = JobRepository(tmp_path / "gui_dl.db")
    repo.enqueue("https://example.com/z")
    worker = SequentialWorker(
        repo,
        download_handler=lambda job, r: r.set_paths(
            job.id, download_path=str(tmp_path / "x.bin")
        ),
        poll_interval=0.02,
    )
    assert worker.is_armed is False
    worker.request_download_all()
    deadline = time.time() + 5
    while time.time() < deadline and repo.count_by_status("completed") < 1:
        time.sleep(0.05)
    assert repo.count_by_status("completed") == 1
    deadline = time.time() + 2
    while time.time() < deadline and worker.is_armed:
        time.sleep(0.05)
    assert worker.is_armed is False
    worker.stop()
    repo.close()
