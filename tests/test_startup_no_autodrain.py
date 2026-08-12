"""Step B2 — startup recovery must not drain leftover pending jobs."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.queue.worker import SequentialWorker
from tests.test_tray_service import _FakeIcon


def test_recover_interrupted_does_not_arm_or_claim_pendings(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    leftover = repo.enqueue("https://example.com/pending")
    crashed = repo.enqueue("https://example.com/crashed")
    repo.update_status(crashed.id, "downloading")
    started: list[int] = []

    def handler(job, r):
        started.append(job.id)
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    recovered = worker.prepare_idle_launch()
    assert crashed.id in recovered
    assert leftover.id not in recovered
    assert repo.get(crashed.id).status == "pending"
    assert repo.get(leftover.id).status == "pending"
    assert worker.is_armed is False
    assert worker.is_running is False
    time.sleep(0.2)
    assert started == []
    assert repo.count_by_status("downloading") == 0
    assert repo.count_by_status("pending") == 2
    worker.stop(timeout=2)
    repo.close()


def test_create_app_recover_does_not_download_pendings(tmp_path: Path):
    try:
        from frameforge.gui.app import create_app
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "g.db")
    pending = repo.enqueue("https://example.com/p")
    crashed = repo.enqueue("https://example.com/c")
    repo.update_status(crashed.id, "downloading")
    try:
        app = create_app(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert repo.get(crashed.id).status == "pending"
        assert repo.get(pending.id).status == "pending"
        assert app.worker.is_armed is False
        assert app.worker.is_running is False
        time.sleep(0.15)
        assert repo.get(pending.id).status == "pending"
        assert repo.count_by_status("downloading") == 0
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            repo.close()
        except Exception:  # noqa: BLE001
            pass
