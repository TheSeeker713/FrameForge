"""Universal recovery ladder: impersonate, cookies, generic (no live network)."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.impersonate import DEFAULT_AUTO_HOSTS, should_impersonate, url_needs_impersonate
from frameforge.download.recovery import (
    format_tried,
    next_recovery_step,
    silent_cookie_import,
)
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.errors import (
    AUTH_REQUIRED,
    DRM_BLOCKED,
    IMPERSONATION_MISSING,
    NOT_AVAILABLE,
    UNKNOWN,
    classify_error,
    format_ytdlp_exit_error,
    should_fail_pause,
)
from frameforge.queue.fail_pause import fail_pause_payload


def test_auto_impersonate_includes_non_ph_hosts():
    assert "xvideos.com" in DEFAULT_AUTO_HOSTS
    assert url_needs_impersonate("https://www.xvideos.com/video.123/title")
    assert url_needs_impersonate("https://www.spankbang.com/abc/video")
    assert not url_needs_impersonate("https://www.youtube.com/watch?v=abc")
    assert not url_needs_impersonate("https://vimeo.com/123")


def test_should_impersonate_auto_for_listed_host(monkeypatch):
    monkeypatch.setattr(
        "frameforge.download.impersonate.list_impersonate_targets",
        lambda: ["chrome-116:windows-10"],
    )
    assert should_impersonate("https://www.xhamster.com/videos/1", mode="auto") is True
    assert should_impersonate("https://example.com/v", mode="auto") is False


def test_recovery_order_impersonate_then_cookies_then_generic():
    url = "https://example.com/v"
    msg = "unsupported url / no suitable extractor"
    step1 = next_recovery_step(
        [],
        category=IMPERSONATION_MISSING,
        message="no impersonate target / TLS fingerprint",
        url=url,
        has_impersonate_targets=True,
    )
    assert step1 == "impersonate"
    step2 = next_recovery_step(
        ["impersonate"],
        category=AUTH_REQUIRED,
        message="login required",
        url=url,
        impersonated=True,
        has_impersonate_targets=True,
        silent_cookies=True,
    )
    assert step2 == "silent_firefox_cookies"
    step3 = next_recovery_step(
        ["impersonate", "silent_firefox_cookies"],
        category=UNKNOWN,
        message=msg,
        url=url,
        impersonated=True,
    )
    assert step3 == "generic"
    assert (
        next_recovery_step(
            ["impersonate", "silent_firefox_cookies", "generic"],
            category=UNKNOWN,
            message=msg,
            url=url,
            impersonated=True,
        )
        is None
    )


def test_generic_retry_only_once_and_skipped_for_drm_unavailable():
    url = "https://example.com/clip"
    assert (
        next_recovery_step(
            ["generic"],
            category=UNKNOWN,
            message="Unsupported URL",
            url=url,
        )
        is None
    )
    assert (
        next_recovery_step(
            [],
            category=DRM_BLOCKED,
            message="DRM protected will NOT be supported",
            url=url,
        )
        is None
    )
    assert (
        next_recovery_step(
            [],
            category=NOT_AVAILABLE,
            message="Video unavailable",
            url=url,
        )
        is None
    )


def test_drm_stderr_classifies_drm_blocked():
    msg = format_ytdlp_exit_error(
        1,
        ["ERROR: This video is DRM protected and will NOT be supported by yt-dlp"],
    )
    assert classify_error(msg) == DRM_BLOCKED
    assert classify_error(msg) != UNKNOWN
    assert should_fail_pause(DRM_BLOCKED) is False


def test_handler_generic_retry_once(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    repo = JobRepository(tmp_path / "r.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    n = {"i": 0}

    def fake_download(url: str, **kwargs: object):
        n["i"] += 1
        if n["i"] == 1:
            assert dl.use_generic_extractors is False
            raise RuntimeError("ERROR: Unsupported URL — no suitable extractor")
        assert dl.use_generic_extractors is True
        path = out / "ok.mp4"
        path.write_bytes(b"x")
        return DownloadResult(path=path, title="ok", info={"extractor_key": "generic", "id": "1"})

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/embed/1")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    assert loaded.options().get("recovery_attempts") == ["generic"]
    assert "generic" in (loaded.options().get("recovery_tried") or "")
    assert loaded.extractor == "generic"
    repo.close()


def test_handler_records_tried_on_final_auth_fail(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])

    def fake_import(_url: str):
        return {"ok": False, "message": "no browser"}

    monkeypatch.setattr(
        "frameforge.download.recovery.silent_cookie_import",
        lambda url, importer=None: silent_cookie_import(url, importer=fake_import),
    )
    repo = JobRepository(tmp_path / "a.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)

    def boom(url: str, **kwargs: object):
        raise RuntimeError("ERROR: login required to download this video")

    dl.download = boom  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/gated")
    repo.update_status(job.id, "downloading")
    try:
        handler(job, repo)
        raise AssertionError("expected failure")
    except RuntimeError:
        pass
    loaded = repo.get(job.id)
    assert "silent_firefox_cookies" in (loaded.options().get("recovery_attempts") or [])
    assert format_tried(loaded.options().get("recovery_attempts")).startswith("tried:")
    repo.close()


def test_fail_pause_payload_includes_tried(tmp_path: Path):
    repo = JobRepository(tmp_path / "f.db")
    job = repo.enqueue("https://example.com/x")
    repo.update_status(job.id, "failed", error="login required")
    repo.merge_options(
        job.id,
        {
            "error_category": AUTH_REQUIRED,
            "recovery_attempts": ["native", "cookies"],
            "recovery_tried": "tried: native, cookies",
        },
    )
    payload = fail_pause_payload(repo.get(job.id))
    assert payload["tried"] == "tried: native, cookies"
    assert payload["recovery_attempts"] == ["native", "cookies"]
    repo.close()


def test_non_yt_non_ph_argv_with_cookies_and_optional_impersonate(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "frameforge.download.impersonate.list_impersonate_targets",
        lambda: ["chrome-116:windows-10"],
    )
    cookie = tmp_path / "example.com.txt"
    cookie.write_text("# Netscape\n.example.com\tTRUE\t/\tFALSE\t0\ta\tb\n", encoding="utf-8")
    dl = YtDlpDownloader(
        output_dir=tmp_path / "o",
        archive_file=tmp_path / "a.txt",
        use_aria2c=False,
        cookiefile=cookie,
    )
    url = "https://example.com/watch?v=1"
    cmd = dl._build_cli_cmd(url)
    assert "--cookies" in cmd
    assert "--impersonate" not in cmd
    dl.force_impersonate = True
    cmd2 = dl._build_cli_cmd(url)
    assert "--impersonate" in cmd2
    assert cmd2[cmd2.index("--impersonate") + 1] == "chrome"
    xv = "https://www.xvideos.com/video.1/title"
    assert "--impersonate" in dl._build_cli_cmd(xv)
