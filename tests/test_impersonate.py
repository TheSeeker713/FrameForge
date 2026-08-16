"""PornHub / MindGeek impersonate argv, classification, and env probe (no live PH)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.impersonate import (
    PINNED_CURL_CFFI,
    impersonate_cli_args,
    impersonate_mode,
    impersonation_status,
    missing_impersonation_error,
    require_impersonate_for_url,
    select_impersonate_client,
    should_impersonate,
    url_needs_impersonate,
)
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.errors import (
    AUTH_REQUIRED,
    IMPERSONATION_MISSING,
    NOT_AVAILABLE,
    UNKNOWN,
    annotate_job_error,
    classify_error,
    format_ytdlp_exit_error,
    should_fail_pause,
    suggested_actions,
)

PH_URL = "https://www.pornhub.com/view_video.php?viewkey=6a5f2e146fdb9"
_CHROME_TARGETS = ["chrome-116:windows-10", "edge-101:windows-10"]

JOB70_STDERR = """\
WARNING: [PornHub] The extractor is attempting impersonated requests, but no impersonate target is available. If you encounter errors, then see https://github.com/yt-dlp/yt-dlp#impersonation for information on installing the required dependencies
ERROR: [PornHub] 6a5f2e146fdb9: Unable to download webpage: HTTP Error 410: Gone
"""

TARGET_UNAVAILABLE = 'ERROR: Impersonate target "chrome" is not available. See --list-impersonate-targets'


def test_url_needs_impersonate_pornhub_family():
    assert url_needs_impersonate(PH_URL)
    assert url_needs_impersonate("https://rt.pornhub.com/view_video.php?viewkey=abc")
    assert url_needs_impersonate("https://www.pornhubpremium.com/video")
    assert url_needs_impersonate("https://www.youporn.com/watch/1/")
    assert not url_needs_impersonate("https://www.youtube.com/watch?v=abc")
    assert not url_needs_impersonate("https://example.com/v")


def test_select_chrome_over_edge():
    assert select_impersonate_client(_CHROME_TARGETS) == "chrome"
    assert select_impersonate_client(["edge-101:windows-10"]) == "edge"
    assert select_impersonate_client([]) is None


def test_pornhub_argv_includes_impersonate_when_targets_mocked(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "frameforge.download.impersonate.list_impersonate_targets",
        lambda: list(_CHROME_TARGETS),
    )
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    cmd = dl._build_cli_cmd(PH_URL)
    assert "--impersonate" in cmd
    assert cmd[cmd.index("--impersonate") + 1] == "chrome"
    snap = dl.describe_cli_invocation(PH_URL)
    assert snap["impersonate"] == "chrome"
    opts = dl.build_opts(url=PH_URL)
    assert opts.get("impersonate") is not None
    yt = dl._build_cli_cmd("https://www.youtube.com/watch?v=abc")
    assert "--impersonate" not in yt


def test_impersonate_mode_always_and_off(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "frameforge.download.impersonate.list_impersonate_targets",
        lambda: list(_CHROME_TARGETS),
    )
    repo = JobRepository(tmp_path / "s.db")
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    dl._settings_repo = repo
    repo.set_setting("impersonate_mode", "off")
    assert impersonate_mode(repo) == "off"
    assert "--impersonate" not in dl._build_cli_cmd(PH_URL)
    repo.set_setting("impersonate_mode", "always")
    yt = dl._build_cli_cmd("https://www.youtube.com/watch?v=abc")
    assert "--impersonate" in yt
    assert impersonate_cli_args(PH_URL, repo=repo)[1] == "chrome"
    repo.close()


def test_require_impersonate_raises_when_targets_missing(monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    with pytest.raises(RuntimeError, match="Impersonate target not available"):
        require_impersonate_for_url(PH_URL)
    assert require_impersonate_for_url("https://example.com/v") is None
    assert "curl_cffi" in missing_impersonation_error()
    assert PINNED_CURL_CFFI in missing_impersonation_error()


def test_handler_pornhub_without_targets_is_impersonation_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.impersonate.list_impersonate_targets", lambda: [])
    repo = JobRepository(tmp_path / "h.db")
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    handler = make_download_handler(dl)
    job = repo.enqueue(PH_URL)
    repo.update_status(job.id, "downloading")
    with pytest.raises(RuntimeError, match="Impersonate target"):
        handler(job, repo)
    repo.close()


def test_classify_job70_stderr_is_not_unknown():
    wrapped = format_ytdlp_exit_error(1, JOB70_STDERR.splitlines())
    assert classify_error(wrapped) == IMPERSONATION_MISSING
    assert classify_error(wrapped) != UNKNOWN
    assert classify_error(TARGET_UNAVAILABLE) == IMPERSONATION_MISSING
    assert classify_error(TARGET_UNAVAILABLE) != UNKNOWN
    assert should_fail_pause(IMPERSONATION_MISSING) is True
    assert any("curl_cffi" in a for a in suggested_actions(IMPERSONATION_MISSING))


def test_classify_410_after_impersonate_and_cookies_is_unavailable():
    msg = format_ytdlp_exit_error(
        1,
        ["ERROR: [PornHub] x: Unable to download webpage: HTTP Error 410: Gone"],
        argv=[
            "python",
            "-m",
            "yt_dlp",
            "--impersonate",
            "chrome",
            "--cookies",
            r"C:\Users\x\Downloads\FrameForge\cookies\pornhub.com.txt",
            PH_URL,
        ],
    )
    assert classify_error(msg, url=PH_URL) == NOT_AVAILABLE
    assert classify_error(msg, url=PH_URL) != UNKNOWN
    assert classify_error(msg, url=PH_URL) != IMPERSONATION_MISSING
    assert should_fail_pause(NOT_AVAILABLE) is False


def test_classify_410_impersonate_without_cookies_is_auth():
    msg = format_ytdlp_exit_error(
        1,
        ["ERROR: [PornHub] x: Unable to download webpage: HTTP Error 410: Gone"],
        argv=["python", "-m", "yt_dlp", "--impersonate", "chrome", PH_URL],
    )
    assert classify_error(msg, url=PH_URL) == AUTH_REQUIRED


def test_annotate_job70_persists_impersonation_missing(tmp_path: Path):
    repo = JobRepository(tmp_path / "j.db")
    job = repo.enqueue(PH_URL)
    annotate_job_error(repo, job.id, format_ytdlp_exit_error(1, JOB70_STDERR.splitlines()))
    loaded = repo.get(job.id)
    assert loaded.options().get("error_category") == IMPERSONATION_MISSING
    assert loaded.options().get("error_category") != UNKNOWN
    repo.close()


def test_should_impersonate_auto_only_adult(monkeypatch):
    monkeypatch.setattr(
        "frameforge.download.impersonate.list_impersonate_targets",
        lambda: list(_CHROME_TARGETS),
    )
    assert should_impersonate(PH_URL, mode="auto") is True
    assert should_impersonate("https://www.youtube.com/watch?v=a", mode="auto") is False
    assert should_impersonate("https://www.youtube.com/watch?v=a", mode="always") is True
    assert should_impersonate(PH_URL, mode="off") is False


def test_impersonation_status_shape():
    st = impersonation_status()
    assert "yt_dlp_version" in st
    assert "curl_cffi_version" in st
    assert "chrome_available" in st
    assert "clients" in st
    assert st["pinned_curl_cffi"] == PINNED_CURL_CFFI
    assert isinstance(st["clients"], list)
