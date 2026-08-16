"""Thread-local SQLite — GUI + worker must not share a Connection."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from frameforge.db.connection import connect, is_transient_sqlite
from frameforge.db.repository import Job, JobRepository
from frameforge.errors import DB_ERROR, UNKNOWN, classify_error, should_fail_pause
from frameforge.queue.worker import SequentialWorker


def test_connect_wal_and_check_same_thread(tmp_path: Path):
    db = tmp_path / "wal.db"
    conn = connect(db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"
    err: list[BaseException] = []

    def other() -> None:
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError as exc:
            err.append(exc)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(timeout=5)
    assert err, "shared Connection must reject the other thread"
    conn.close()
    assert db.exists()
    assert db.stat().st_size > 0


def test_repo_thread_local_connections_are_distinct(tmp_path: Path):
    db = tmp_path / "jobs.db"
    repo = JobRepository(db)
    main_conn = repo.conn
    other: dict[str, sqlite3.Connection] = {}

    def on_worker() -> None:
        other["conn"] = repo.conn
        repo.list_jobs()

    thread = threading.Thread(target=on_worker)
    thread.start()
    thread.join(timeout=5)
    assert "conn" in other
    assert other["conn"] is not main_conn

    captured = repo.conn
    err: list[BaseException] = []

    def misuse() -> None:
        try:
            captured.execute("SELECT 1")
        except sqlite3.ProgrammingError as exc:
            err.append(exc)

    bad = threading.Thread(target=misuse)
    bad.start()
    bad.join(timeout=5)
    assert err
    repo.close()


def test_operationalerror_is_db_error_not_unknown():
    nested = "cannot start a transaction within a transaction"
    locked = "sqlite3.OperationalError: database is locked"
    assert classify_error(nested) == DB_ERROR
    assert classify_error(nested) != UNKNOWN
    assert classify_error(locked) == DB_ERROR
    assert classify_error(locked) != UNKNOWN
    assert should_fail_pause(DB_ERROR) is False
    assert is_transient_sqlite(sqlite3.OperationalError(nested))
    assert is_transient_sqlite(sqlite3.OperationalError("database is locked"))


def test_concurrent_list_progress_claim_does_not_fail_jobs(tmp_path: Path):
    db = tmp_path / "conc.db"
    repo = JobRepository(db)
    jobs = [repo.enqueue(f"https://example.com/{i}", title=str(i)) for i in range(8)]

    def handler(job: Job, r: JobRepository) -> None:
        for pct in (10.0, 40.0, 70.0, 100.0):
            r.update_progress(job.id, pct)
            time.sleep(0.01)
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.01)
    stop = threading.Event()
    errors: list[BaseException] = []

    def reader() -> None:
        try:
            while not stop.is_set():
                repo.list_jobs()
                repo.count_by_status("pending")
                repo.count_by_status("downloading")
                time.sleep(0.005)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def progress_writer() -> None:
        try:
            while not stop.is_set():
                for job in repo.list_jobs("downloading"):
                    repo.update_progress(job.id, min(99.0, float(job.progress) + 0.1))
                time.sleep(0.005)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    threads += [threading.Thread(target=progress_writer) for _ in range(2)]
    for thread in threads:
        thread.start()
    worker.request_download_all()
    deadline = time.time() + 30
    while time.time() < deadline:
        if all(repo.get(j.id).status == "completed" for j in jobs):
            break
        time.sleep(0.05)
    stop.set()
    for thread in threads:
        thread.join(timeout=5)
    worker.stop(timeout=5)
    assert not errors, errors
    for job in jobs:
        loaded = repo.get(job.id)
        assert loaded.status == "completed", (loaded.status, loaded.error)
        err = (loaded.error or "").lower()
        assert "sqlite" not in err
        assert "cannot start a transaction" not in err
        assert loaded.options().get("error_category") not in {DB_ERROR, UNKNOWN, "unknown"}
    assert db.exists()
    assert db.stat().st_size > 0
    repo.close()


def test_worker_loop_operationalerror_does_not_fail_job(tmp_path: Path):
    repo = JobRepository(tmp_path / "loop.db")

    def handler(job: Job, r: JobRepository) -> None:
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    orig = worker._process_one
    calls = {"n": 0}

    def boom_once() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("cannot start a transaction within a transaction")
        return orig()

    worker._process_one = boom_once  # type: ignore[method-assign]
    job = repo.enqueue("https://example.com/ok")
    worker.request_download_ids([job.id])
    deadline = time.time() + 15
    while time.time() < deadline:
        if repo.get(job.id).status == "completed":
            break
        time.sleep(0.05)
    loaded = repo.get(job.id)
    assert loaded.status == "completed", loaded.error
    assert loaded.options().get("error_category") not in {UNKNOWN, "unknown"}
    worker.stop(timeout=5)
    repo.close()


def test_handler_locked_sqlite_requeues_then_completes(tmp_path: Path):
    repo = JobRepository(tmp_path / "requeue.db")
    calls = {"n": 0}

    def handler(job: Job, r: JobRepository) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    job = repo.enqueue("https://example.com/lock")
    worker.request_download_ids([job.id])
    deadline = time.time() + 15
    while time.time() < deadline:
        if repo.get(job.id).status == "completed":
            break
        time.sleep(0.05)
    loaded = repo.get(job.id)
    assert loaded.status == "completed", loaded.error
    assert calls["n"] >= 2
    assert loaded.options().get("error_category") not in {UNKNOWN, "unknown"}
    worker.stop(timeout=5)
    repo.close()


def test_exhausted_sqlite_retries_are_db_error_not_unknown(tmp_path: Path):
    repo = JobRepository(tmp_path / "exhausted.db")

    def handler(job: Job, r: JobRepository) -> None:
        raise sqlite3.OperationalError("database is locked")

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    job = repo.enqueue("https://example.com/always-lock")
    worker.request_download_ids([job.id])
    deadline = time.time() + 20
    while time.time() < deadline:
        if repo.get(job.id).status == "failed":
            break
        time.sleep(0.05)
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert loaded.options().get("error_category") == DB_ERROR
    assert classify_error(loaded.error) == DB_ERROR
    assert classify_error(loaded.error) != UNKNOWN
    worker.stop(timeout=5)
    repo.close()
