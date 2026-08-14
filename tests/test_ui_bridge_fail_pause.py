"""Phase B — headless UiBridge: enqueue does not arm; retry-fail-again fail-pauses."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from frameforge.download.cookie_validate import clear_session_cookie_validation
from frameforge.download.cookies import cookie_path_for_url
from frameforge.db.repository import JobRepository
from frameforge.errors import BOT_CHECK, UNKNOWN, annotate_job_error, format_ytdlp_exit_error
from frameforge.queue.fail_pause import maybe_fail_pause
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.bridge import UiBridge


def test_enqueue_does_not_arm_worker(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    started: list[int] = []

    def handler(job, r):
        started.append(job.id)

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    bridge = UiBridge(repo, worker)
    job = bridge.enqueue_url("https://example.com/a", title="a")
    assert job.status == "pending"
    assert worker.is_armed is False
    time.sleep(0.15)
    assert started == []
    assert repo.get(job.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()


def test_retry_fail_again_uses_same_fail_pause_handler(tmp_path: Path):
    repo = JobRepository(tmp_path / "r.db")
    seen: list[int] = []

    def boom(job, r):
        raise RuntimeError("Sign in to confirm you’re not a bot")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.02)
    bridge = UiBridge(repo, worker)
    bridge.set_fail_pause_handler(lambda job, payload: seen.append(int(payload["job_id"])))
    first = bridge.enqueue_url("https://www.youtube.com/watch?v=a", title="a")
    second = bridge.enqueue_url("https://www.youtube.com/watch?v=b", title="b")
    assert worker.is_armed is False
    worker.request_download_ids([first.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    assert repo.get(second.id).status == "pending"
    assert worker.is_armed is False
    assert seen == [first.id]
    opts = repo.get(first.id).options()
    assert opts.get("error_category") == BOT_CHECK
    assert opts.get("error_cause")
    assert opts.get("error_stderr_tail")

    bridge.handle_fail_pause_action("retry", first.id)
    deadline = time.time() + 8
    while time.time() < deadline and (
        repo.get(first.id).status in ("pending", "downloading") or len(seen) < 2
    ):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    assert repo.get(second.id).status == "pending"
    assert worker.is_armed is False
    assert seen == [first.id, first.id]
    worker.stop(timeout=2)
    repo.close()


def test_unknown_exit_code_fail_pauses(tmp_path: Path):
    repo = JobRepository(tmp_path / "u.db")
    job = repo.enqueue("https://example.com/u")
    msg = format_ytdlp_exit_error(1, ["[debug] ...", "ERROR: unexplained extractor crash"])
    annotate_job_error(repo, job.id, msg)
    loaded = repo.get(job.id)
    assert loaded.options().get("error_category") == UNKNOWN
    assert loaded.options().get("error_cause")
    assert "extractor crash" in (loaded.options().get("error_stderr_tail") or "")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    assert maybe_fail_pause(worker, repo, loaded) is True
    assert worker.is_armed is False
    repo.close()


def test_bridge_fail_pause_authenticate_uses_job_url(tmp_path: Path):
    repo = JobRepository(tmp_path / "a.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    bridge = UiBridge(repo, worker)
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="gated")
    annotate_job_error(repo, job.id, "Sign in to confirm you’re not a bot")
    urls: list[str | None] = []
    bridge.handle_fail_pause_action("authenticate", job.id, authenticate=lambda u: urls.append(u))
    assert urls == [job.url]
    requested: list[list[int]] = []
    worker.request_download_ids = lambda ids: requested.append(list(ids))  # type: ignore[method-assign]
    worker.request_download_all = lambda: requested.append(["all"])  # type: ignore[method-assign]
    clear_session_cookie_validation()
    dest = cookie_path_for_url(job.url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tx\n",
        encoding="utf-8",
    )
    bridge.cookie_probe = lambda url, cookiefile: {"id": "abc", "title": "ok"}
    bridge.handle_fail_pause_action(
        "import_browser",
        job.id,
        import_browser=lambda u: SimpleNamespace(ok=True, message="imported"),
        ask_retry_resume=lambda: True,
    )
    assert requested == [[job.id]]
    assert repo.get(job.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()
