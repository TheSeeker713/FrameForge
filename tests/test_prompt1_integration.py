"""Step 5.1 — Prompt 1 cross-feature integration matrix."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.browser_import import import_cookies_from_browser
from frameforge.download.cookies import resolve_cookiefile_for_url
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.gui.exit_policy import (
    CHOICE_CANCEL_AND_QUIT,
    CHOICE_PAUSE_AND_QUIT,
    CHOICE_WAIT_THEN_QUIT,
    apply_quit_choice,
)
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker
from frameforge.util.process_tree import DownloadPaused
from tests.test_browser_cookie_import import VALID_NETSCAPE
from tests.test_tray_service import _FakeIcon


def test_pause_quit_reopen_resume_complete(tmp_path: Path):
    db = tmp_path / "m.db"
    out = tmp_path / "dl"
    out.mkdir()
    part = out / "clip.mp4.part"
    calls = {"n": 0}

    def handler(job, r):
        calls["n"] += 1
        r.merge_options(job.id, {"download_output_dir": str(out)})
        if r.get(job.id).options().get("paused_from") or calls["n"] == 1:
            if calls["n"] == 1:
                part.write_bytes(b"partial")
                r.set_paths(job.id, download_path=str(part))
                while r.get(job.id).status == "downloading":
                    time.sleep(0.02)
                raise DownloadPaused("paused")
        final = out / "clip.mp4"
        final.write_bytes(b"done")
        r.set_paths(job.id, download_path=str(final), output_path=str(final))

    repo = JobRepository(db)
    job = repo.enqueue("https://example.com/int")
    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    worker.request_download_ids([job.id])
    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status != "downloading":
        time.sleep(0.02)
    assert repo.get(job.id).status == "downloading"
    assert apply_quit_choice(worker, CHOICE_PAUSE_AND_QUIT) == "exit"
    job_id = job.id
    worker.stop(timeout=3)
    repo.close()

    repo2 = JobRepository(db)
    assert repo2.get(job_id).status == "paused"
    worker2 = SequentialWorker(repo2, download_handler=handler, poll_interval=0.02)
    worker2.resume_job(job_id)
    deadline = time.time() + 15
    while time.time() < deadline:
        if repo2.get(job_id).status == "completed":
            break
        time.sleep(0.05)
    loaded = repo2.get(job_id)
    assert loaded.status == "completed", loaded.error
    assert loaded.download_path and Path(loaded.download_path).exists()
    worker2.stop(timeout=3)
    repo2.close()


def test_quit_cancel_active_and_wait_disarms(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    active = repo.enqueue("https://example.com/a")
    queued = repo.enqueue("https://example.com/b")
    repo.claim_next_pending()
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    worker._armed.set()
    assert apply_quit_choice(worker, CHOICE_CANCEL_AND_QUIT) == "exit"
    assert repo.get(active.id).status == "cancelled"
    assert repo.get(queued.id).status == "pending"
    assert worker.is_armed is False

    repo.update_status(active.id, "downloading")
    worker._armed.set()
    other = repo.enqueue("https://example.com/c")
    assert apply_quit_choice(worker, CHOICE_WAIT_THEN_QUIT) == "wait"
    assert worker.wait_to_quit is True
    assert worker.is_armed is False
    assert repo.get(other.id).status == "pending"
    repo.close()


def test_tray_hide_does_not_auto_start(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "t.db")
    repo.set_setting("close_to_tray", "1")
    pending = repo.enqueue("https://example.com/p")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert app.worker.is_armed is False
        app._on_window_close()
        assert app._shutting_down is False
        assert app.worker.is_armed is False
        assert repo.get(pending.id).status == "pending"
        assert repo.count_by_status("downloading") == 0
    finally:
        app._shutting_down = True
        try:
            app.tray.stop(timeout=1)
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            repo.close()
        except Exception:  # noqa: BLE001
            pass


def test_browser_import_used_on_next_download_opts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        dest = Path(cmd[cmd.index("--cookies") + 1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(VALID_NETSCAPE, encoding="utf-8")
        return 0, "", ""

    result = import_cookies_from_browser("https://example.com/v", browser="firefox", runner=runner)
    assert result.ok
    cookie = resolve_cookiefile_for_url("https://example.com/v")
    assert cookie is not None
    dl = YtDlpDownloader(
        output_dir=tmp_path / "o",
        archive_file=tmp_path / "a.txt",
        use_aria2c=False,
        cookiefile=cookie,
    )
    opts = dl.build_opts()
    assert opts.get("cookiefile") == str(cookie)
    cmd = dl._build_cli_cmd("https://example.com/v")
    assert "--cookies" in cmd
    assert str(cookie) in cmd
