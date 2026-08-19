"""Worker-thread retry backoff (no UI sleep, no live network)."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.recovery import (
    BOT_RETRY,
    SILENT_FIREFOX_COOKIES,
    apply_auto_retry_backoff,
    auto_retry_backoff_jitter_sec,
    auto_retry_backoff_sec,
    compute_retry_delay,
    interruptible_backoff,
    next_recovery_step,
    waiting_label,
)
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.errors import BOT_CHECK, NOT_AVAILABLE, RATE_LIMITED
from frameforge.queue.worker import SequentialWorker
from frameforge.util.process_tree import DownloadPaused


def _clip_result(out: Path) -> DownloadResult:
    path = out / "ok.mp4"
    path.write_bytes(b"x")
    return DownloadResult(path=path, title="ok", info={"extractor_key": "generic", "id": "1"})


def test_interruptible_backoff_zero_and_complete_and_abort():
    assert interruptible_backoff(0, lambda: False) is True
    t0 = time.monotonic()
    assert interruptible_backoff(0.2, lambda: False) is True
    assert time.monotonic() - t0 >= 0.15
    t1 = time.monotonic()
    assert interruptible_backoff(8.0, lambda: True) is False
    assert time.monotonic() - t1 < 0.5


def test_backoff_settings_clamp(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    repo.set_setting("auto_retry_backoff_sec", "99")
    repo.set_setting("auto_retry_backoff_jitter_sec", "40")
    assert auto_retry_backoff_sec(repo) == 60.0
    assert auto_retry_backoff_jitter_sec(repo) == 15.0
    repo.set_setting("auto_retry_backoff_sec", "-3")
    repo.set_setting("auto_retry_backoff_jitter_sec", "x")
    assert auto_retry_backoff_sec(repo) == 0.0
    assert auto_retry_backoff_jitter_sec(repo) == 2.0
    repo.close()


def test_compute_retry_delay_zero_base_ignores_jitter(tmp_path: Path, monkeypatch):
    repo = JobRepository(tmp_path / "d.db")
    repo.set_setting("auto_retry_backoff_sec", "0")
    repo.set_setting("auto_retry_backoff_jitter_sec", "15")
    monkeypatch.setattr("frameforge.download.recovery.random.uniform", lambda a, b: 1.5)
    assert compute_retry_delay(repo) == 0.0
    repo.set_setting("auto_retry_backoff_sec", "5")
    repo.set_setting("auto_retry_backoff_jitter_sec", "2")
    assert compute_retry_delay(repo) == 6.5
    repo.close()


def test_waiting_label():
    assert waiting_label(5.0) == "Waiting 5s before retry…"
    assert waiting_label(7.2) == "Waiting 7.2s before retry…"


def test_rate_limited_tries_cookies_then_bot_retry_if_cookies_skipped():
    url = "https://example.com/x"
    msg = "HTTP Error 429: Too Many Requests"
    assert (
        next_recovery_step(
            [],
            category=RATE_LIMITED,
            message=msg,
            url=url,
            silent_cookies=True,
        )
        == SILENT_FIREFOX_COOKIES
    )
    assert (
        next_recovery_step(
            [],
            category=RATE_LIMITED,
            message=msg,
            url=url,
            silent_cookies=False,
        )
        == BOT_RETRY
    )
    assert (
        next_recovery_step(
            [BOT_RETRY],
            category=RATE_LIMITED,
            message=msg,
            url=url,
            silent_cookies=False,
        )
        is None
    )
    assert (
        next_recovery_step(
            [],
            category=BOT_CHECK,
            message="Sign in to confirm you’re not a bot",
            url="https://example.com/x",
            silent_cookies=False,
        )
        == BOT_RETRY
    )
    assert (
        next_recovery_step(
            [SILENT_FIREFOX_COOKIES],
            category=BOT_CHECK,
            message="Sign in to confirm you’re not a bot",
            url="https://example.com/x",
            silent_cookies=False,
        )
        is None
    )
    assert (
        next_recovery_step(
            [],
            category=NOT_AVAILABLE,
            message="Video unavailable",
            url="https://example.com/x",
        )
        is None
    )


def test_backoff_sec_zero_no_sleep_retry_once(tmp_path: Path, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: waits.append(seconds) or True,
    )
    repo = JobRepository(tmp_path / "z.db")
    repo.set_setting("auto_retry_backoff_sec", "0")
    repo.set_setting("auto_retry_backoff_jitter_sec", "2")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("ERROR: login required to download this video")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/gated")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    assert waits == []
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert not any(str(a).startswith("backoff:") for a in attempts)
    repo.close()


def test_backoff_invoked_records_attempt(tmp_path: Path, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: waits.append(seconds) or True,
    )
    repo = JobRepository(tmp_path / "b.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("ERROR: login required to download this video")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/gated")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    assert waits == [2.0]
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert "backoff:2.0" in attempts
    assert attempts.count("backoff:2.0") == 1
    repo.close()


def test_cancel_during_backoff_no_retry(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    repo = JobRepository(tmp_path / "c.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("ERROR: login required to download this video")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    job_box: dict[str, int] = {}

    def fake_wait(seconds: float, should_abort):
        repo.update_status(job_box["id"], "cancelled")
        return False

    monkeypatch.setattr("frameforge.download.recovery.interruptible_backoff", fake_wait)
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    job = repo.enqueue("https://example.com/gated")
    job_box["id"] = job.id
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    loaded = repo.get(job.id)
    assert loaded.status == "cancelled"
    assert n["i"] == 1
    assert paused == []
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert not any(str(a).startswith("backoff:") for a in attempts)
    worker.stop(timeout=2)
    repo.close()


def test_pause_during_backoff_no_retry(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )

    def fake_wait(seconds: float, should_abort):
        repo.update_status(job.id, "paused")
        return False

    monkeypatch.setattr("frameforge.download.recovery.interruptible_backoff", fake_wait)
    repo = JobRepository(tmp_path / "p.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("ERROR: login required to download this video")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/gated")
    repo.update_status(job.id, "downloading")
    try:
        handler(job, repo)
        raise AssertionError("expected pause abort")
    except DownloadPaused:
        pass
    assert n["i"] == 1
    assert repo.get(job.id).status == "paused"
    repo.close()


def test_apply_backoff_skipped_when_already_recorded(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: (_ for _ in ()).throw(AssertionError("must not sleep twice")),
    )
    repo = JobRepository(tmp_path / "once.db")
    repo.set_setting("auto_retry_backoff_sec", "5")
    attempts = ["silent_firefox_cookies", "backoff:5.0"]
    assert (
        apply_auto_retry_backoff(repo=repo, attempts=attempts, job_id=1, progress_cb=None)
        is True
    )
    assert attempts == ["silent_firefox_cookies", "backoff:5.0"]
    repo.close()


def test_rate_limited_auto_retry_uses_cookies_then_backoff(tmp_path: Path, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: waits.append(seconds) or True,
    )
    repo = JobRepository(tmp_path / "r.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("HTTP Error 429: Too Many Requests")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/hot")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    assert waits == [2.0]
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert BOT_RETRY not in attempts
    assert "backoff:2.0" in attempts
    repo.close()
