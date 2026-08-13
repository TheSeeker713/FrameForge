"""Step 3.2 — auth/bot failure disarms the worker and does not drain remaining pendings."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.errors import BOT_CHECK, annotate_job_error
from frameforge.queue.fail_pause import fail_pause_payload, maybe_fail_pause
from frameforge.queue.worker import SequentialWorker


def test_fail_pause_payload_has_cause_and_actions():
    job = Job(
        id=1,
        url="https://www.youtube.com/watch?v=x",
        title="gated",
        status="failed",
        priority=0,
        progress=0,
        error="Sign in to confirm you’re not a bot",
        output_path=None,
        download_path=None,
        format_preference="best",
        upscale=False,
        created_at="",
        updated_at="",
        started_at=None,
        finished_at=None,
        options_json=None,
    )
    payload = fail_pause_payload(job)
    assert payload["category"] == BOT_CHECK
    assert "bot" in payload["cause"].lower()
    assert payload["url"].startswith("https://")
    ids = [b["id"] for b in payload["buttons"]]
    assert ids == ["import_browser", "authenticate", "retry", "skip_resume", "stop"]


def test_auth_failure_disarms_and_leaves_pending(tmp_path: Path):
    repo = JobRepository(tmp_path / "fp.db")
    seen: list[dict] = []

    def boom(job: Job, r: JobRepository) -> None:
        raise RuntimeError("Sign in to confirm you’re not a bot")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.02)
    worker.on_fail_pause = lambda job: seen.append(fail_pause_payload(job))
    first = repo.enqueue("https://www.youtube.com/watch?v=a", title="a")
    second = repo.enqueue("https://www.youtube.com/watch?v=b", title="b")
    worker.request_download_ids([first.id, second.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    assert repo.get(second.id).status == "pending"
    assert worker.is_armed is False
    assert seen and seen[0]["job_id"] == first.id
    time.sleep(0.2)
    assert repo.get(second.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()


def test_network_failure_does_not_fail_pause(tmp_path: Path):
    repo = JobRepository(tmp_path / "n.db")
    job = repo.enqueue("https://example.com/n")
    annotate_job_error(repo, job.id, "Connection reset by peer")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    loaded = repo.get(job.id)
    assert maybe_fail_pause(worker, repo, loaded) is False
    assert worker.is_armed is False
    repo.close()
