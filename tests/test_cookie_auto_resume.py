"""Validated cookies resume the queue without the fail-pause dialog."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.cookie_validate import mark_cookies_validated
from frameforge.errors import annotate_job_error
from frameforge.queue.fail_pause import fail_pause_payload
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi


def test_validated_cookies_retry_without_a_dialog(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")

    def ok(job, _repo):
        return None

    worker = SequentialWorker(repo, download_handler=ok, poll_interval=0.02)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    job = ui.bridge.enqueue_url("https://example.com/watch?v=auto1")
    annotate_job_error(repo, job.id, "decoder widget exploded for no classified reason")
    mark_cookies_validated(job.url)
    payload = fail_pause_payload(repo.get(job.id))
    ui._on_fail_pause(repo.get(job.id), payload)
    assert ui.fail_pause_shown == 0
    assert ui.dialogs.kind != "fail_pause"
    assert repo.get(job.id).status in {"pending", "downloading", "completed"}
    ui.shutdown()


def test_second_failure_after_auto_resume_still_pauses(tmp_path: Path):
    repo = JobRepository(tmp_path / "c2.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    job = ui.bridge.enqueue_url("https://example.com/watch?v=auto2")
    annotate_job_error(repo, job.id, "decoder widget exploded for no classified reason")
    mark_cookies_validated(job.url)
    ui._cookie_auto_resume_ids.add(job.id)
    ui._on_fail_pause(repo.get(job.id), fail_pause_payload(repo.get(job.id)))
    assert ui.fail_pause_shown == 1
    assert repo.get(job.id).status == "failed"
    ui.shutdown()
