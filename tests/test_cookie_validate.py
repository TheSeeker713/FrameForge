"""Cookie validate-before-resume and gentle cooldown after bot recovery."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.cookie_validate import (
    GENTLE_AFTER_BOT_JOBS,
    UNLOCK_FAIL,
    clear_session_cookie_validation,
    consume_gentle_job,
    cookies_validated_in_session,
    enable_gentle_after_bot,
    validate_cookies_for_url,
)
from frameforge.download.cookies import cookie_path_for_url
from frameforge.errors import annotate_job_error
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.bridge import UiBridge


def _write_cookies(url: str) -> Path:
    path = cookie_path_for_url(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tx\n",
        encoding="utf-8",
    )
    return path


def test_validate_rejects_missing_and_bot_probe():
    clear_session_cookie_validation()
    url = "https://missing-cookies.example.test/watch?v=missing"
    leftover = cookie_path_for_url(url)
    if leftover.exists():
        leftover.unlink()
    miss = validate_cookies_for_url(url, probe=lambda u, p: {"id": "x"})
    assert miss.ok is False
    assert "No valid Netscape" in miss.message

    _write_cookies(url)
    failed = validate_cookies_for_url(
        url,
        probe=lambda u, p: (_ for _ in ()).throw(RuntimeError("Sign in to confirm you’re not a bot")),
    )
    assert failed.ok is False
    assert failed.probed is True
    assert UNLOCK_FAIL in failed.message


def test_validate_success_session_reuse_skips_second_probe():
    clear_session_cookie_validation()
    url = "https://www.youtube.com/watch?v=okcookie"
    _write_cookies(url)
    probes: list[str] = []

    def probe(u, p):
        probes.append(u)
        return {"id": "vid", "title": "ok"}

    first = validate_cookies_for_url(url, probe=probe)
    assert first.ok is True
    assert first.probed is True
    assert cookies_validated_in_session(url)
    second = validate_cookies_for_url(url, probe=probe)
    assert second.ok is True
    assert second.probed is False
    assert probes == [url]


def test_recover_then_retry_resume_does_not_arm_on_import(tmp_path: Path):
    clear_session_cookie_validation()
    repo = JobRepository(tmp_path / "r.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    bridge = UiBridge(repo, worker)
    job = repo.enqueue("https://www.youtube.com/watch?v=rec")
    annotate_job_error(repo, job.id, "Sign in to confirm you’re not a bot")
    url = job.url
    _write_cookies(url)
    bridge.cookie_probe = lambda u, p: {"id": "rec", "title": "ok"}
    recovered = bridge.recover_bot_cookies(
        url,
        import_browser=lambda u: type("R", (), {"ok": True, "message": "imported"})(),
    )
    assert recovered["ok"] is True
    assert worker.is_armed is False
    assert int(repo.get_setting("gentle_jobs_left", "0")) == GENTLE_AFTER_BOT_JOBS
    armed: list[str] = []
    worker.request_download_ids = lambda ids: armed.append("ids")  # type: ignore[method-assign]
    worker.request_download_all = lambda: armed.append("all")  # type: ignore[method-assign]
    bridge.retry_and_resume(job.id)
    assert repo.get(job.id).status == "pending"
    assert armed == ["ids", "all"]
    worker.stop(timeout=2)
    repo.close()


def test_gentle_jobs_left_consumes_without_permanent_setting(tmp_path: Path):
    repo = JobRepository(tmp_path / "g.db")
    enable_gentle_after_bot(repo, 2)
    assert consume_gentle_job(repo) is True
    assert consume_gentle_job(repo) is True
    assert consume_gentle_job(repo) is False
    assert repo.get_setting("gentle_rate_mode", "0") == "0"
    repo.close()
