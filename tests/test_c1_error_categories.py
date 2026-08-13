"""C1 — structured error categories persisted on jobs."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.errors import (
    AUTH_REQUIRED,
    BLOCKED_4K,
    BOT_CHECK,
    CANCELLED,
    FFMPEG,
    NETWORK,
    NOT_AVAILABLE,
    RATE_LIMITED,
    UNKNOWN,
    annotate_job_error,
    classify_error,
    human_cause,
    should_fail_pause,
    suggested_actions,
)
from frameforge.queue.worker import SequentialWorker


def test_classify_error_known_messages():
    assert classify_error("Sign in to confirm you’re not a bot") == BOT_CHECK
    assert classify_error("HTTP Error 403: Forbidden") == AUTH_REQUIRED
    assert classify_error("Blocked: source is 4K/≥2160p (height=2160)") == BLOCKED_4K
    assert classify_error("ffmpeg failed: No such file or directory") == FFMPEG
    assert classify_error("ffprobe: Invalid data found") == FFMPEG
    assert classify_error("Connection reset by peer") == NETWORK
    assert classify_error("Failed to resolve 'example.invalid'") == NETWORK
    assert classify_error("HTTP Error 429: Too Many Requests") == RATE_LIMITED
    assert classify_error("Video unavailable") == NOT_AVAILABLE
    assert classify_error("This video is private") == NOT_AVAILABLE
    assert classify_error("cancelled", status="cancelled") == CANCELLED
    assert classify_error("Download cancelled by user") == CANCELLED
    assert classify_error("yt-dlp exited with code 1") == UNKNOWN
    assert classify_error(None) == UNKNOWN
    assert should_fail_pause(BOT_CHECK) is True
    assert should_fail_pause(AUTH_REQUIRED) is True
    assert should_fail_pause(NETWORK) is False
    assert "cookies" in human_cause(AUTH_REQUIRED).lower() or "signed in" in human_cause(AUTH_REQUIRED).lower()
    assert any("browser" in a.lower() for a in suggested_actions(BOT_CHECK))


def test_annotate_job_error_persists_category(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    job = repo.enqueue("https://example.com/x")
    annotate_job_error(repo, job.id, "Blocked: source is 4K/≥2160p (height=2160)")
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert loaded.options().get("error_category") == BLOCKED_4K
    assert loaded.options().get("auth_required") is False
    assert "2160" in (loaded.error or "")

    auth = repo.enqueue("https://www.youtube.com/watch?v=z")
    annotate_job_error(repo, auth.id, "login required")
    a2 = repo.get(auth.id)
    assert a2.options().get("error_category") == AUTH_REQUIRED
    assert a2.options().get("auth_required") is True
    repo.close()


def test_worker_failure_writes_category(tmp_path: Path):
    repo = JobRepository(tmp_path / "w.db")

    def boom(job, r):
        raise RuntimeError("Connection reset by peer")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.01)
    job = repo.enqueue("https://example.com/n")
    worker.request_download_ids([job.id])
    import time

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert loaded.options().get("error_category") == NETWORK
    worker.stop(timeout=5)
    repo.close()
