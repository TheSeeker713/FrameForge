"""v0.5.4 — Pause/Stop while armed; fail-pause must not claim the next bulk job."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.errors import annotate_job_error
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi, build_header
from frameforge.ui_flet.queue_chrome import queue_chrome_spec
from tests.flet_fakes import FakePage


def _ui(tmp_path: Path) -> FrameForgeUi:
    repo = JobRepository(tmp_path / "t.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    return FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)


def test_chrome_shows_pause_stop_when_armed_or_downloading(tmp_path: Path):
    ui = _ui(tmp_path)
    ui.page = FakePage()
    ui.build()
    pending = ui.bridge.enqueue_url("https://example.com/p")
    ui.refresh_queue(force=True)
    idle = ui.queue_chrome.data
    assert idle["show_pause"] is False
    assert idle["show_stop"] is False
    assert idle["show_download_all"] is True
    assert ui.header.data["pause"].visible is False

    ui.repo.update_status(pending.id, "downloading")
    ui.worker._armed.set()
    ui.refresh_queue(force=True)
    armed = ui.queue_chrome.data
    assert armed["show_pause"] is True
    assert armed["show_stop"] is True
    assert armed["show_download_all"] is False
    assert ui.header.data["pause"].visible is True
    assert ui.header.data["stop"].visible is True
    assert ui.header.data["pause"].on_click is not None
    assert ui.header.data["stop"].on_click is not None
    ui.shutdown()


def test_header_transport_buttons_default_hidden():
    header = build_header()
    assert header.data["pause"].visible is False
    assert header.data["stop"].visible is False
    header_on = build_header(show_pause=True, show_stop=True, on_pause=lambda: None, on_stop=lambda: None)
    assert header_on.data["pause"].visible is True
    assert header_on.data["stop"].visible is True


def test_pause_and_stop_handlers_disarm_and_leave_pending(tmp_path: Path):
    ui = _ui(tmp_path)
    first = ui.repo.enqueue("https://example.com/a")
    second = ui.repo.enqueue("https://example.com/b")
    ui.repo.update_status(first.id, "downloading")
    ui.worker._armed.set()
    ui.pause_active()
    assert ui.repo.get(first.id).status == "paused"
    assert ui.repo.get(second.id).status == "pending"
    assert ui.worker.is_armed is False

    ui.repo.update_status(first.id, "pending", error=None, progress=0)
    ui.repo.update_status(first.id, "downloading")
    ui.worker._armed.set()
    ui.stop_active()
    assert ui.repo.get(first.id).status == "cancelled"
    assert ui.repo.get(second.id).status == "pending"
    assert ui.worker.is_armed is False
    ui.shutdown()


def test_unknown_fail_on_first_does_not_claim_second(tmp_path: Path):
    repo = JobRepository(tmp_path / "bulk.db")
    claimed: list[int] = []

    def boom(job: Job, r: JobRepository) -> None:
        claimed.append(job.id)
        raise RuntimeError("ERROR: [generic] unknown extractor failure")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.02)
    first = repo.enqueue("https://example.com/one")
    second = repo.enqueue("https://example.com/two")
    worker.request_download_all()
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    time.sleep(0.25)
    assert repo.get(second.id).status == "pending"
    assert claimed == [first.id]
    assert worker.is_armed is False
    assert worker.is_fail_paused is True
    assert worker._process_one() is False
    worker._armed.set()
    assert worker._process_one() is False
    assert repo.get(second.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()


def test_handler_failed_without_raise_still_halt_bulk(tmp_path: Path):
    repo = JobRepository(tmp_path / "silent.db")

    def mark_failed(job: Job, r: JobRepository) -> None:
        annotate_job_error(r, job.id, "yt-dlp exited with unknown error")

    worker = SequentialWorker(repo, download_handler=mark_failed, poll_interval=0.02)
    first = repo.enqueue("https://example.com/one")
    second = repo.enqueue("https://example.com/two")
    worker.request_download_all()
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    time.sleep(0.25)
    assert repo.get(second.id).status == "pending"
    assert worker.is_fail_paused is True
    worker.stop(timeout=2)
    repo.close()


def test_explicit_skip_resume_clears_halt_and_claims_next(tmp_path: Path):
    repo = JobRepository(tmp_path / "skip.db")
    n = {"i": 0}

    def sometimes(job: Job, r: JobRepository) -> None:
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("Sign in to confirm you’re not a bot")

    worker = SequentialWorker(repo, download_handler=sometimes, poll_interval=0.02)
    first = repo.enqueue("https://example.com/one")
    second = repo.enqueue("https://example.com/two")
    worker.request_download_all()
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    assert worker.is_fail_paused is True
    worker.request_download_all()
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(second.id).status != "completed":
        time.sleep(0.03)
    assert repo.get(second.id).status == "completed"
    assert repo.get(first.id).status == "failed"
    worker.stop(timeout=2)
    repo.close()


def test_chrome_spec_transport_keys_independent_of_jobs():
    spec = queue_chrome_spec([], set())
    assert spec["show_pause"] is False
    assert spec["show_stop"] is False
    spec_armed = queue_chrome_spec(
        [type("J", (), {"status": "pending", "id": 1})()],
        set(),
        armed=True,
    )
    assert spec_armed["show_pause"] is True
    assert spec_armed["show_stop"] is True
    assert spec_armed["show_download_all"] is False
