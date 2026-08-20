"""Auto Firefox cookie recovery before fail-pause (no live network)."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.recovery import (
    RETRY,
    SILENT_FIREFOX_COOKIES,
    next_recovery_step,
    should_try_silent_cookies,
    silent_cookies_enabled,
)
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.errors import (
    AUTH_REQUIRED,
    BOT_CHECK,
    DB_ERROR,
    DISK_SPACE,
    DRM_BLOCKED,
    JS_RUNTIME,
    NETWORK,
    NOT_AVAILABLE,
    RATE_LIMITED,
    UNKNOWN,
    UPSCALE_CONFIG,
    classify_error,
)
from frameforge.queue.fail_pause import fail_pause_payload
from frameforge.queue.worker import SequentialWorker


PH_URL = "https://www.pornhub.com/view_video.php?viewkey=abc"
YT_URL = "https://www.youtube.com/watch?v=dQw4w9wg"
FIXTURE_URL = "https://example.video/watch?v=1"
AUTH_MSG = "ERROR: login required to download this video"
BARE_UNKNOWN = "yt-dlp exited with code 1\nno stderr; see invocation log"


def _clip_result(out: Path) -> DownloadResult:
    path = out / "ok.mp4"
    path.write_bytes(b"x")
    return DownloadResult(path=path, title="ok", info={"extractor_key": "pornhub", "id": "1"})


def test_ph_age_and_unknown_classify():
    assert classify_error("ERROR: [PornHub] Please verify your age to continue.") == AUTH_REQUIRED
    assert classify_error("ERROR: login required") == AUTH_REQUIRED
    assert classify_error("Sign in to confirm you’re not a bot") == BOT_CHECK
    assert classify_error(BARE_UNKNOWN) == UNKNOWN
    assert should_try_silent_cookies(AUTH_REQUIRED, AUTH_MSG, YT_URL) is True
    assert should_try_silent_cookies(AUTH_REQUIRED, AUTH_MSG, FIXTURE_URL) is True
    assert should_try_silent_cookies(AUTH_REQUIRED, AUTH_MSG, PH_URL) is True
    assert should_try_silent_cookies(RATE_LIMITED, "HTTP Error 429: Too Many Requests", YT_URL) is True
    assert should_try_silent_cookies(UNKNOWN, "please sign in to continue", YT_URL) is True
    assert should_try_silent_cookies(UNKNOWN, BARE_UNKNOWN, PH_URL) is True
    assert should_try_silent_cookies(
        UNKNOWN, BARE_UNKNOWN, "https://ff-no-cookies-test.invalid/watch"
    ) is False
    assert (
        next_recovery_step(
            ["impersonate"],
            category=UNKNOWN,
            message=BARE_UNKNOWN,
            url=PH_URL,
            impersonated=True,
            silent_cookies=True,
        )
        == SILENT_FIREFOX_COOKIES
    )
    assert (
        next_recovery_step(
            ["impersonate"],
            category=UNKNOWN,
            message=BARE_UNKNOWN,
            url=YT_URL,
            impersonated=True,
            silent_cookies=True,
        )
        == SILENT_FIREFOX_COOKIES
    )
    assert should_try_silent_cookies(UNKNOWN, BARE_UNKNOWN, YT_URL) is False
    assert (
        next_recovery_step(
            [],
            category=UNKNOWN,
            message=BARE_UNKNOWN,
            url=YT_URL,
            silent_cookies=True,
        )
        is None
    )


def test_do_not_auto_recover_skip_categories():
    msg = "anything"
    assert should_try_silent_cookies(NOT_AVAILABLE, "Video unavailable", YT_URL) is False
    assert should_try_silent_cookies(NOT_AVAILABLE, "Video unavailable", PH_URL) is False
    assert should_try_silent_cookies(DRM_BLOCKED, "DRM protected", FIXTURE_URL) is False
    assert should_try_silent_cookies(DISK_SPACE, "not enough disk", YT_URL) is False
    assert should_try_silent_cookies(DB_ERROR, "database is locked", YT_URL) is False
    assert should_try_silent_cookies(JS_RUNTIME, "n challenge solving failed", YT_URL) is False
    assert should_try_silent_cookies(UPSCALE_CONFIG, "no onnx model", YT_URL) is False
    assert should_try_silent_cookies(NETWORK, "connection reset", YT_URL) is False
    assert should_try_silent_cookies("cancelled", msg, PH_URL) is False
    assert (
        next_recovery_step(
            [],
            category=NOT_AVAILABLE,
            message="Video unavailable",
            url=YT_URL,
            silent_cookies=True,
        )
        is None
    )


def test_setting_auto_cookie_recovery_off(tmp_path: Path):
    repo = JobRepository(tmp_path / "s.db")
    assert silent_cookies_enabled(repo) is True
    repo.set_setting("auto_cookie_recovery", "0")
    assert silent_cookies_enabled(repo) is False
    repo.close()


def test_silent_firefox_success_retries_once_no_fail_pause(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    repo = JobRepository(tmp_path / "ok.db")
    repo.set_setting("auto_retry_backoff_sec", "0")
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
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    job = repo.enqueue("https://example.com/gated")
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    loaded = repo.get(job.id)
    assert loaded.status == "completed"
    assert n["i"] == 2
    assert paused == []
    assert worker.is_fail_paused is False
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert attempts.count(SILENT_FIREFOX_COOKIES) == 1
    assert RETRY in attempts
    assert "Cookies refreshed" in (loaded.options().get("recovery_toast") or "")
    worker.stop(timeout=2)
    repo.close()


def test_ph_auth_enters_silent_cookie_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.impersonate.require_impersonate_for_url",
        lambda url, repo=None: None,
    )
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    waits: list[float] = []
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: waits.append(seconds) or True,
    )
    repo = JobRepository(tmp_path / "ph.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("ERROR: [PornHub] Please verify your age to continue.")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue(PH_URL)
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert "backoff:2.0" in attempts
    assert RETRY in attempts
    repo.close()


def test_unknown_after_impersonate_runs_firefox_then_retry_no_fail_pause(tmp_path: Path, monkeypatch):
    """Field regression: category unknown + tried impersonate must not open the modal."""
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: ["chrome"])
    monkeypatch.setattr(
        "frameforge.download.impersonate.require_impersonate_for_url",
        lambda url, repo=None: "chrome",
    )

    def slow_import(url: str, importer=None):
        time.sleep(0.1)
        return {"ok": True, "browser": "firefox"}

    monkeypatch.setattr("frameforge.download.recovery.silent_cookie_import", slow_import)
    repo = JobRepository(tmp_path / "field.db")
    repo.set_setting("auto_retry_backoff_sec", "0")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        dl.last_invocation = {"impersonate": "chrome"}
        if n["i"] == 1:
            raise RuntimeError(BARE_UNKNOWN)
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    job = repo.enqueue(PH_URL)
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    loaded = repo.get(job.id)
    assert loaded.status == "completed"
    assert n["i"] == 2
    assert paused == []
    attempts = loaded.options().get("recovery_attempts") or []
    assert "impersonate" in attempts
    assert SILENT_FIREFOX_COOKIES in attempts
    assert RETRY in attempts
    assert attempts.index("impersonate") < attempts.index(SILENT_FIREFOX_COOKIES)
    assert attempts.index(SILENT_FIREFOX_COOKIES) < attempts.index(RETRY)
    worker.stop(timeout=2)
    repo.close()


def test_youtube_auth_silent_cookies_backoff_no_fail_pause(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.js_runtime.require_js_runtime_for_url",
        lambda url: "deno",
    )
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    waits: list[float] = []
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: waits.append(seconds) or True,
    )
    repo = JobRepository(tmp_path / "yt.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError(AUTH_MSG)
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    job = repo.enqueue(YT_URL)
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    loaded = repo.get(job.id)
    assert loaded.status == "completed"
    assert n["i"] == 2
    assert paused == []
    assert waits == [2.0]
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert "backoff:2.0" in attempts
    assert RETRY in attempts
    worker.stop(timeout=2)
    repo.close()


def test_example_video_host_same_cookie_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": True, "browser": "firefox"},
    )
    waits: list[float] = []
    monkeypatch.setattr(
        "frameforge.download.recovery.interruptible_backoff",
        lambda seconds, should_abort: waits.append(seconds) or True,
    )
    repo = JobRepository(tmp_path / "ev.db")
    repo.set_setting("auto_retry_backoff_sec", "2")
    repo.set_setting("auto_retry_backoff_jitter_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError(AUTH_MSG)
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue(FIXTURE_URL)
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    attempts = loaded.options().get("recovery_attempts") or []
    assert SILENT_FIREFOX_COOKIES in attempts
    assert "backoff:2.0" in attempts
    assert RETRY in attempts
    repo.close()


def test_silent_import_fail_invokes_fail_pause(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: {"ok": False, "message": "Firefox not found"},
    )
    repo = JobRepository(tmp_path / "fail.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)

    def boom(url: str, **kwargs: object):
        raise RuntimeError("ERROR: login required to download this video")

    dl.download = boom  # type: ignore[method-assign]
    paused: list[dict] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(fail_pause_payload(job))
    job = repo.enqueue("https://example.com/gated")
    pending = repo.enqueue("https://example.com/next")
    worker.request_download_ids([job.id, pending.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    loaded = repo.get(job.id)
    assert loaded.status == "failed"
    assert repo.get(pending.id).status == "pending"
    assert paused and paused[0]["job_id"] == job.id
    assert SILENT_FIREFOX_COOKIES in (paused[0].get("recovery_attempts") or [])
    assert worker.is_fail_paused is True
    time.sleep(0.15)
    assert repo.get(pending.id).status == "pending"
    worker.stop(timeout=2)
    repo.close()


def test_one_silent_import_per_failure_chain():
    step = next_recovery_step(
        [SILENT_FIREFOX_COOKIES],
        category=AUTH_REQUIRED,
        message="login required",
        url=PH_URL,
        silent_cookies=True,
    )
    assert step != SILENT_FIREFOX_COOKIES
    step_legacy = next_recovery_step(
        ["cookies"],
        category=AUTH_REQUIRED,
        message="login required",
        url="https://example.com/x",
        silent_cookies=True,
    )
    assert step_legacy != SILENT_FIREFOX_COOKIES


def test_ui_toast_once_from_recovery_note(tmp_path: Path):
    from frameforge.ui_flet.app import FrameForgeUi

    repo = JobRepository(tmp_path / "ui.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    job = repo.enqueue("https://example.com/x")
    repo.merge_options(job.id, {"recovery_toast": "Cookies refreshed (Firefox) — retrying…"})
    ui._maybe_recovery_toast(repo.get(job.id))
    assert ui.last_toast and "Firefox" in ui.last_toast
    ui._maybe_recovery_toast(repo.get(job.id))
    assert ui.last_toast.count("Firefox") >= 1
    ui.shutdown()
    repo.close()


def test_auto_cookie_recovery_off_pending_downloads_without_firefox(tmp_path: Path, monkeypatch):
    firefox: list[str] = []
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None, timeout_sec=None: firefox.append(url) or {"ok": False},
    )
    repo = JobRepository(tmp_path / "off.db")
    repo.set_setting("auto_cookie_recovery", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    job = repo.enqueue("https://example.com/plain")
    worker.request_download_ids([job.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(job.id).status == "completed"
    assert n["i"] == 1
    assert firefox == []
    worker.stop(timeout=2)
    repo.close()


def test_silent_firefox_timeout_fail_pause_worker_accepts_later_arm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None, timeout_sec=None: {
            "ok": False,
            "stage": "timeout",
            "message": "Cookie import timed out after 60s",
        },
    )
    repo = JobRepository(tmp_path / "to.db")
    repo.set_setting("auto_retry_backoff_sec", "0")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)

    def fake_download(url: str, **kwargs: object):
        if "gated" in url:
            raise RuntimeError("ERROR: login required to download this video")
        return _clip_result(out)

    dl.download = fake_download  # type: ignore[method-assign]
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    first = repo.enqueue("https://example.com/gated")
    second = repo.enqueue("https://example.com/next")
    worker.request_download_ids([first.id, second.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(first.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(first.id).status == "failed"
    assert repo.get(second.id).status == "pending"
    assert paused == [first.id]
    assert worker.is_fail_paused is True
    worker.request_download_ids([second.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(second.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(second.id).status == "completed"
    assert worker.is_fail_paused is False
    worker.stop(timeout=2)
    repo.close()


def test_silent_success_halt_cleared_second_pending_runs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None, timeout_sec=None: {"ok": True, "browser": "firefox"},
    )
    repo = JobRepository(tmp_path / "two.db")
    repo.set_setting("auto_retry_backoff_sec", "0")
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
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    first = repo.enqueue("https://example.com/gated")
    second = repo.enqueue("https://example.com/next")
    worker.request_download_all()
    deadline = time.time() + 8
    while time.time() < deadline:
        s1 = repo.get(first.id).status
        s2 = repo.get(second.id).status
        if s1 == "completed" and s2 == "completed":
            break
        time.sleep(0.03)
    assert repo.get(first.id).status == "completed"
    assert repo.get(second.id).status == "completed"
    assert n["i"] == 3
    assert paused == []
    assert worker.is_fail_paused is False
    attempts = repo.get(first.id).options().get("recovery_attempts") or []
    assert attempts.count(SILENT_FIREFOX_COOKIES) == 1
    assert RETRY in attempts
    worker.stop(timeout=2)
    repo.close()


def test_recover_browser_cookies_timeout_does_not_block(monkeypatch):
    from frameforge.download.browser_import import BrowserImportResult
    from frameforge.download.recovery import recover_browser_cookies

    calls: list[str | None] = []

    def hang(url, *, browser=None, timeout=None, runner=None):
        calls.append(browser)
        time.sleep(0.05)
        return BrowserImportResult(False, f"cookie import timed out after {float(timeout or 0):.0f}s")

    monkeypatch.setattr(
        "frameforge.download.browser_import.import_cookies_from_browser",
        hang,
    )
    started = time.monotonic()
    result = recover_browser_cookies(
        "https://example.com/x",
        timeout_sec=0.25,
        file_only=True,
    )
    elapsed = time.monotonic() - started
    assert result["ok"] is False
    assert result["stage"] == "timeout"
    assert elapsed < 3
    assert calls


def test_recovery_exception_fail_pauses_worker_stays_alive(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])

    def boom(url, importer=None, timeout_sec=None):
        raise RuntimeError("firefox import exploded")

    monkeypatch.setattr("frameforge.download.recovery.silent_cookie_import", boom)
    repo = JobRepository(tmp_path / "boom.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)

    def fail(url: str, **kwargs: object):
        raise RuntimeError("ERROR: login required to download this video")

    dl.download = fail  # type: ignore[method-assign]
    paused: list[int] = []
    worker = SequentialWorker(
        repo,
        download_handler=make_download_handler(dl),
        poll_interval=0.02,
    )
    worker.on_fail_pause = lambda job: paused.append(job.id)
    job = repo.enqueue("https://example.com/gated")
    later = repo.enqueue("https://example.com/next")
    worker.request_download_ids([job.id, later.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(job.id).status == "failed"
    assert paused == [job.id]
    assert worker.is_running is True
    dl.download = lambda url, **kwargs: _clip_result(out)  # type: ignore[method-assign]
    worker.request_download_ids([later.id])
    deadline = time.time() + 8
    while time.time() < deadline and repo.get(later.id).status in ("pending", "downloading"):
        time.sleep(0.03)
    assert repo.get(later.id).status == "completed"
    worker.stop(timeout=2)
    repo.close()
