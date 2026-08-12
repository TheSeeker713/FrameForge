"""A2 — failure-driven auth hints; cookies still resolve; non-auth stays quiet."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download import cookies as cookie_mod
from frameforge.download.auth_hints import (
    AUTH_ACTION_LABEL,
    apply_auth_failure,
    auth_action_hint,
    is_auth_failure,
    job_needs_auth,
)
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.gui.app import FrameForgeApp
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker


AUTH_SAMPLES = [
    "ERROR: [youtube] abc: Sign in to confirm you’re not a bot",
    "Sign in to confirm you are not a bot",
    "HTTP Error 401: Unauthorized",
    "HTTP Error 403: Forbidden",
    "This video is age-restricted and requires cookies",
    "This video is members-only",
    "Use --cookies-from-browser or --cookies",
    "login required to download this video",
]

NON_AUTH_SAMPLES = [
    "Blocked: source is 4K/≥2160p (height=2160)",
    "yt-dlp exited with code 1",
    "Download skipped or failed (no info returned)",
    "cancelled",
    "Failed to resolve 'example.invalid'",
    "Connection reset by peer",
    "ffmpeg failed: No such file or directory",
]


def test_auth_failure_strings_map_to_hint():
    for msg in AUTH_SAMPLES:
        assert is_auth_failure(msg), msg
    for msg in NON_AUTH_SAMPLES:
        assert not is_auth_failure(msg), msg
    assert not is_auth_failure(None)
    assert not is_auth_failure("")


def test_apply_auth_failure_stores_structured_hint(tmp_path: Path):
    repo = JobRepository(tmp_path / "a.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="gated")
    apply_auth_failure(
        repo,
        job.id,
        "ERROR: Sign in to confirm you’re not a bot",
        job.url,
    )
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert "not a bot" in (loaded.error or "")
    opts = loaded.options()
    assert opts.get("auth_required") is True
    assert opts.get("auth_domain") == "youtube.com"
    assert AUTH_ACTION_LABEL in (opts.get("auth_hint") or "")
    assert job_needs_auth(loaded)
    panel = FrameForgeApp.format_error_panel_text(loaded)
    assert "not a bot" in panel
    assert AUTH_ACTION_LABEL in panel
    repo.close()


def test_non_auth_failure_does_not_trigger_hint(tmp_path: Path):
    repo = JobRepository(tmp_path / "n.db")
    job = repo.enqueue("https://example.com/clip")
    repo.update_status(job.id, "failed", error="Blocked: source is 4K/≥2160p (height=2160)")
    loaded = repo.get(job.id)
    assert not job_needs_auth(loaded)
    panel = FrameForgeApp.format_error_panel_text(loaded)
    assert AUTH_ACTION_LABEL not in panel
    assert "2160" in panel
    repo.close()


def test_existing_cookies_still_resolve_cookiefile(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    src = tmp_path / "exported.txt"
    src.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc\n",
        encoding="utf-8",
    )
    dest = cookie_mod.import_netscape_cookies("youtube.com", src)
    resolved = cookie_mod.resolve_cookiefile_for_url("https://www.youtube.com/watch?v=1")
    assert resolved is not None
    assert resolved == dest
    dl = YtDlpDownloader(
        output_dir=tmp_path / "o", archive_file=tmp_path / "a.txt", use_aria2c=False
    )
    dl.cookiefile = resolved
    opts = dl.build_opts(None)
    assert opts.get("cookiefile") == str(resolved)
    hint = auth_action_hint("https://www.youtube.com/watch?v=1")
    assert "already exist" in hint
    assert "Import to replace" in hint


def test_worker_auth_exception_annotates_job(tmp_path: Path):
    repo = JobRepository(tmp_path / "w.db")

    def boom(job, r):
        raise RuntimeError("HTTP Error 403: Forbidden — Sign in to confirm you’re not a bot")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.01)
    job = repo.enqueue("https://www.youtube.com/watch?v=gated")
    worker.request_download_ids([job.id])
    import time

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status == "pending":
        time.sleep(0.02)
    # wait until not downloading
    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status == "downloading":
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert job_needs_auth(loaded)
    assert loaded.options().get("auth_required") is True
    worker.stop(timeout=5)
    repo.close()


def test_worker_non_auth_exception_has_no_auth_flag(tmp_path: Path):
    repo = JobRepository(tmp_path / "x.db")

    def boom(job, r):
        raise RuntimeError("ffmpeg failed: No such file or directory")

    worker = SequentialWorker(repo, download_handler=boom, poll_interval=0.01)
    job = repo.enqueue("https://example.com/clip")
    worker.request_download_ids([job.id])
    import time

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert not job_needs_auth(loaded)
    assert not loaded.options().get("auth_required")
    worker.stop(timeout=5)
    repo.close()


def test_error_panel_auth_button_enabled_for_auth_job(tmp_path: Path):
    import pytest

    try:
        repo = JobRepository(tmp_path / "g.db")
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert hasattr(app, "auth_from_job_btn")
        ok = repo.enqueue("https://example.com/ok")
        gated = repo.enqueue("https://www.youtube.com/watch?v=x")
        apply_auth_failure(
            repo,
            gated.id,
            "Sign in to confirm you’re not a bot",
            gated.url,
        )
        app.refresh_queue()
        app.queue_list.set_selected({ok.id})
        app._on_selection_changed({ok.id})
        assert str(app.auth_from_job_btn.cget("state")) == "disabled"

        app.queue_list.set_selected({gated.id})
        app._on_selection_changed({gated.id})
        assert str(app.auth_from_job_btn.cget("state")) == "normal"
        shown = app.error_panel.get("1.0", "end-1c")
        assert AUTH_ACTION_LABEL in shown
        assert "not a bot" in shown
    finally:
        app.destroy()
        repo.close()
