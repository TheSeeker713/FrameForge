"""Cancel is typed DownloadCancelled / user status — never English in str(exc)."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.errors import CANCELLED, NOT_AVAILABLE, UNKNOWN, classify_error, should_fail_pause
from frameforge.gui.actions import can_retry_download
from frameforge.queue.worker import SequentialWorker
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused

UPLOADER_CANCELLED = "ERROR: [youtube] This live event was Cancelled by the uploader"


def test_worker_source_has_no_cancelled_substring_control_flow():
    text = Path("src/frameforge/queue/worker.py").read_text(encoding="utf-8")
    assert '"cancelled" in str(exc)' not in text
    assert "'cancelled' in str(exc)" not in text
    assert "in str(exc).lower()" not in text


def test_uploader_cancelled_stderr_is_not_available():
    wrapped = f"yt-dlp exited with code 1\n{UPLOADER_CANCELLED}"
    assert classify_error(wrapped) == NOT_AVAILABLE
    assert classify_error(wrapped) != CANCELLED
    assert classify_error(wrapped) != UNKNOWN
    assert classify_error(UPLOADER_CANCELLED, status="downloading") == NOT_AVAILABLE
    assert should_fail_pause(NOT_AVAILABLE) is False


def test_worker_uploader_cancelled_marks_failed_not_cancelled(tmp_path: Path):
    repo = JobRepository(tmp_path / "up.db")

    def boom(job: Job, r: JobRepository) -> None:
        raise RuntimeError(UPLOADER_CANCELLED)

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.02)
    job = repo.enqueue("https://www.youtube.com/watch?v=livegone")
    worker.request_download_ids([job.id])
    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert loaded.status != "cancelled"
    assert "Cancelled by the uploader" in (loaded.error or "")
    assert loaded.options().get("error_category") == NOT_AVAILABLE
    assert can_retry_download(loaded) is True
    worker.stop(timeout=5)
    repo.close()


def test_user_cancel_typed_exception_stays_cancelled(tmp_path: Path):
    repo = JobRepository(tmp_path / "uc.db")

    def handler(job: Job, r: JobRepository) -> None:
        deadline = time.time() + 8
        while time.time() < deadline:
            if r.get(job.id).status == "cancelled":
                raise DownloadCancelled("cancelled")
            time.sleep(0.02)
        raise TimeoutError("cancel never arrived")

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    job = repo.enqueue("https://example.com/user-cancel")
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status != "downloading":
        time.sleep(0.02)
    assert repo.get(job.id).status == "downloading"
    worker.cancel_job(job.id)
    deadline = time.time() + 8
    while time.time() < deadline:
        if any(e.stage == "download_cancel" and e.job_id == job.id for e in worker.events):
            break
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "cancelled"
    assert loaded.options().get("error_category") == CANCELLED
    worker.stop(timeout=5)
    repo.close()


def test_pause_mid_flight_still_preserved(tmp_path: Path):
    repo = JobRepository(tmp_path / "p.db")

    def handler(job: Job, r: JobRepository) -> None:
        deadline = time.time() + 8
        while time.time() < deadline:
            if r.get(job.id).status == "paused":
                raise DownloadPaused("paused")
            time.sleep(0.02)
        raise TimeoutError("pause never arrived")

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    job = repo.enqueue("https://example.com/pause")
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status != "downloading":
        time.sleep(0.02)
    assert repo.get(job.id).status == "downloading"
    worker.pause_job(job.id)
    deadline = time.time() + 8
    while time.time() < deadline:
        if any(e.stage == "download_pause" and e.job_id == job.id for e in worker.events):
            break
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "paused"
    assert loaded.status != "cancelled"
    assert loaded.status != "failed"
    worker.stop(timeout=5)
    repo.close()
