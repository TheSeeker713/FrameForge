"""v0.5.5 — Cancel/Stop during Starting… (before first % / before Popen)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.ui_flet.queue_chrome import queue_chrome_spec
from frameforge.util.process_tree import DownloadCancelled
from tests.flet_fakes import FakePage


def test_kill_before_pid_still_marks_cancelled():
    reg = ProcessRegistry()
    assert reg.kill(7) is True
    assert reg.was_killed(7) is True
    assert reg.pid_for(7) is None


def test_cancel_before_first_progress_terminates_and_disarms(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    started = threading.Event()
    progressed = {"n": 0}

    def handler(job: Job, r: JobRepository) -> None:
        started.set()
        deadline = time.time() + 8
        while time.time() < deadline:
            current = r.get(job.id)
            if current.status == "cancelled":
                raise DownloadCancelled("cancelled")
            time.sleep(0.03)
        progressed["n"] += 1

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    first = repo.enqueue("https://example.com/slow")
    second = repo.enqueue("https://example.com/next")
    worker.request_download_all()
    assert started.wait(5)
    assert repo.get(first.id).status == "downloading"
    worker.stop_run()
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status == "downloading":
        time.sleep(0.03)
    assert repo.get(first.id).status == "cancelled"
    assert repo.get(second.id).status == "pending"
    assert worker.is_armed is False
    assert progressed["n"] == 0
    worker.stop(timeout=2)
    repo.close()


def test_chrome_shows_stop_when_armed_pending_starting(tmp_path: Path):
    repo = JobRepository(tmp_path / "q.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    ui.build()
    ui.bridge.enqueue_url("https://example.com/p")
    worker._armed.set()
    ui._activity_note = "Starting 1 pending download(s)…"
    ui.refresh_queue(force=True)
    spec = queue_chrome_spec(ui.queue_jobs(), set(), armed=True)
    assert spec["show_stop"] is True
    assert spec["show_pause"] is True
    assert ui.header.data["stop"].visible is True
    ui.shutdown()
