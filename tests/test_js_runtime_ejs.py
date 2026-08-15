"""Deno/EJS: argv flags, classifier fixtures, copy report runtime hint."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.js_runtime import (
    JS_RUNTIME_FIX,
    detect_js_runtime,
    js_runtime_cli_args,
    missing_js_runtime_error,
    require_js_runtime_for_url,
    url_needs_js_runtime,
)
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.error_report import format_full_error_report
from frameforge.errors import (
    JS_RUNTIME,
    UNKNOWN,
    annotate_job_error,
    classify_error,
    should_fail_pause,
    suggested_actions,
)

_EJS_FIXTURES = (
    "ERROR: n challenge solving failed",
    "ERROR: Signature solving failed",
    "ERROR: Only images are available",
    "Please install a JS runtime and the challenge solver script distribution (yt-dlp-ejs)",
    "See https://github.com/yt-dlp/yt-dlp/wiki/EJS",
    "yt-dlp exited with code 1\nERROR: [youtube] xxx: Only images are available; requested format is not available",
)


def test_url_needs_js_runtime():
    assert url_needs_js_runtime("https://www.youtube.com/watch?v=abc")
    assert url_needs_js_runtime("https://youtu.be/abc")
    assert not url_needs_js_runtime("https://example.com/v")


def test_js_runtime_args_node_and_deno(monkeypatch):
    monkeypatch.setattr("frameforge.download.js_runtime.detect_js_runtime", lambda: "node")
    monkeypatch.setattr("frameforge.download.js_runtime.which_on_augmented_path", lambda n: r"C:\n\node.exe" if n == "node" else None)
    args = js_runtime_cli_args("node")
    assert args[0] == "--js-runtimes"
    assert args[1] in {"node", r"node:C:\n\node.exe"} or args[1].startswith("node:")
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    cmd = dl._build_cli_cmd("https://www.youtube.com/watch?v=x")
    assert "--js-runtimes" in cmd
    spec = cmd[cmd.index("--js-runtimes") + 1]
    assert spec == "node" or spec.startswith("node:")

    monkeypatch.setattr("frameforge.download.js_runtime.detect_js_runtime", lambda: "deno")
    monkeypatch.setattr("frameforge.download.js_runtime.which_on_augmented_path", lambda n: r"C:\d\deno.exe" if n == "deno" else None)
    cmd2 = dl._build_cli_cmd("https://www.youtube.com/watch?v=x")
    assert "--js-runtimes" in cmd2
    spec2 = cmd2[cmd2.index("--js-runtimes") + 1]
    assert spec2 == "deno" or spec2.startswith("deno:")
    assert js_runtime_cli_args("deno")[0] == "--js-runtimes"


def test_classify_ejs_stderr_is_js_runtime_not_unknown():
    for blob in _EJS_FIXTURES:
        cat = classify_error(blob)
        assert cat == JS_RUNTIME, blob
        assert cat != UNKNOWN
    actions = suggested_actions(JS_RUNTIME)
    assert actions
    assert not any("re-authenticate" in a.lower() or "authenticate" in a.lower() for a in actions)
    assert any("deno" in a.lower() for a in actions)
    assert should_fail_pause(JS_RUNTIME) is True


def test_copy_report_includes_runtime_hint(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="clip")
    annotate_job_error(repo, job.id, "ERROR: n challenge solving failed")
    repo.merge_options(
        job.id,
        {
            "ytdlp_invocation": {
                "argv": ["python", "-m", "yt_dlp", "https://www.youtube.com/watch?v=abc"],
                "cwd": str(tmp_path),
                "cookies": None,
                "aria2c": False,
                "format": "bv*+ba/b",
                "js_runtime": None,
                "yt_dlp_version": "2025.01.01",
            }
        },
    )
    text = format_full_error_report(repo.get(job.id))
    assert "js_runtime" in text
    assert "Deno" in text or "yt-dlp-ejs" in text
    assert JS_RUNTIME_FIX.split("pip install")[0].strip()[:20] in text or "yt-dlp-ejs" in text
    assert "js_runtime" in text.lower()
    assert classify_error(repo.get(job.id).error) == JS_RUNTIME
    repo.close()


def test_youtube_without_runtime_fails_before_download(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.js_runtime.detect_js_runtime", lambda: None)
    called = []

    def fake_download(url: str, **kwargs: object):
        called.append(url)
        raise AssertionError("yt-dlp must not start without a JS runtime")

    out = tmp_path / "dl"
    out.mkdir()
    repo = JobRepository(tmp_path / "j.db")
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://www.youtube.com/watch?v=abc")
    repo.update_status(job.id, "downloading")
    try:
        handler(job, repo)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert classify_error(str(exc)) == JS_RUNTIME
        assert "deno" in str(exc).lower() or "js runtime" in str(exc).lower()
    assert called == []
    repo.close()


def test_non_youtube_skips_js_requirement(monkeypatch):
    monkeypatch.setattr("frameforge.download.js_runtime.detect_js_runtime", lambda: None)
    assert require_js_runtime_for_url("https://example.com/v") is None
    assert missing_js_runtime_error()
    # detect may be deno on this host; function still exists
    assert detect_js_runtime() is None or detect_js_runtime() in {"deno", "node"}
