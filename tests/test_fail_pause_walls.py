"""Only a real login, bot, runtime, or disk wall pauses the queue."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.error_report import format_full_error_report
from frameforge.errors import (
    AUTH_REQUIRED,
    BOT_CHECK,
    DISK_SPACE,
    DRM_BLOCKED,
    EMPTY_DOWNLOAD,
    IMPERSONATION_MISSING,
    JS_RUNTIME,
    NETWORK,
    NOT_AVAILABLE,
    UNKNOWN,
    annotate_job_error,
    should_fail_pause,
)
from frameforge.queue.fail_pause import maybe_fail_pause, modal_actions_for


def test_pause_categories_are_only_real_walls():
    for cat in (AUTH_REQUIRED, BOT_CHECK, JS_RUNTIME, IMPERSONATION_MISSING, DISK_SPACE):
        assert should_fail_pause(cat) is True
    for cat in (UNKNOWN, EMPTY_DOWNLOAD, NOT_AVAILABLE, NETWORK, DRM_BLOCKED):
        assert should_fail_pause(cat) is False


def test_unknown_modal_has_no_cookie_buttons():
    ids = [aid for aid, _label in modal_actions_for(UNKNOWN)]
    assert "import_browser" not in ids
    assert "authenticate" not in ids
    assert "retry" in ids


def test_copy_report_reads_the_job_log(tmp_path: Path):
    repo = JobRepository(tmp_path / "jobs.db")
    job = repo.enqueue("https://example.com/clip")
    annotate_job_error(repo, job.id, "WARNING: Only images are available\nERROR: boom")
    loaded = repo.get(job.id)
    report = format_full_error_report(loaded)
    assert "job_log:" in report
    assert "Only images are available" in report
    repo.close()


def test_unknown_failure_does_not_halt_the_worker(tmp_path: Path):
    repo = JobRepository(tmp_path / "q.db")
    job = repo.enqueue("https://example.com/v")
    annotate_job_error(repo, job.id, "yt-dlp exited with code 1\nno stderr")

    class _Worker:
        def __init__(self) -> None:
            self.halted = False

        def halt_after_fail(self) -> None:
            self.halted = True

    worker = _Worker()
    assert maybe_fail_pause(worker, repo, repo.get(job.id)) is False
    assert worker.halted is False
    repo.close()
