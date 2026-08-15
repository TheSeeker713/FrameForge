"""v0.5.8 — aria2 HTTP 403 / exit 22 is not FFmpeg; auto native fallback."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.errors import (
    ARIA2_FORBIDDEN,
    AUTH_REQUIRED,
    FFMPEG,
    NETWORK,
    classify_error,
    format_ytdlp_exit_error,
    is_aria2_forbidden,
    should_fail_pause,
)
from frameforge.queue.fail_pause import maybe_fail_pause
from frameforge.queue.worker import SequentialWorker

# Job 74-style stderr: googlevideo 403 + aria2c exit 22 (0 bytes).
ARIA2_403_STDERR = """\
[download] Destination: clip.mp4
ERROR: unable to download video data: HTTP Error 403: Forbidden
ERROR: aria2c exited with code 22
[#1 SIZE:0B/10MiB CN:16 DL:0B]
status=403
URI: https://rr2---sn-abc.googlevideo.com/videoplayback?id=x
"""


def test_aria2_403_is_not_ffmpeg_or_auth():
    msg = format_ytdlp_exit_error(
        1,
        ARIA2_403_STDERR.splitlines(),
        argv=[
            "python",
            "-m",
            "yt_dlp",
            "--ffmpeg-location",
            r"C:\ffmpeg\bin",
            "--downloader",
            "aria2c",
            "https://www.youtube.com/watch?v=x",
        ],
    )
    assert is_aria2_forbidden(msg)
    assert classify_error(msg) == ARIA2_FORBIDDEN
    assert classify_error(msg) != FFMPEG
    assert classify_error(msg) != AUTH_REQUIRED
    assert should_fail_pause(ARIA2_FORBIDDEN) is False
    assert classify_error("HTTP Error 403: Forbidden") == AUTH_REQUIRED
    assert classify_error("ffmpeg failed: No such file or directory") == FFMPEG
    argv_only = format_ytdlp_exit_error(
        1,
        ["ERROR: unable to download video data"],
        argv=["python", "-m", "yt_dlp", "--ffmpeg-location", r"C:\ffmpeg\bin"],
    )
    assert classify_error(argv_only) != FFMPEG


def test_native_retry_argv_omits_aria2_and_restores_default(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.invocation.aria2c_available", lambda: True)
    dl = YtDlpDownloader(
        output_dir=tmp_path,
        archive_file=tmp_path / "a.txt",
        use_aria2c=True,
    )
    assert "--downloader" in dl._build_cli_cmd("https://www.youtube.com/watch?v=x")
    n = {"i": 0}
    notes: list[str] = []

    def fake_inprocess(url: str, progress_cb=None):
        n["i"] += 1
        if n["i"] == 1:
            assert "--downloader" in dl._build_cli_cmd(url)
            raise RuntimeError(ARIA2_403_STDERR)
        cmd = dl._build_cli_cmd(url)
        assert "--downloader" not in cmd
        assert not any(str(a).startswith("aria2c:") for a in cmd)
        path = tmp_path / "ok.mp4"
        path.write_bytes(b"media")
        return DownloadResult(path=path, title="ok", info={})

    def progress_cb(pct: float, meta: dict | None = None) -> None:
        notes.append(str((meta or {}).get("speed_str") or ""))

    dl._download_inprocess = fake_inprocess  # type: ignore[method-assign]
    result = dl.download("https://www.youtube.com/watch?v=x", progress_cb=progress_cb)
    assert n["i"] == 2
    assert result.title == "ok"
    assert dl.aria2_fallback_native is True
    assert dl.download_attempt == 2
    assert dl.download_method == "native"
    assert dl.use_aria2c is True
    assert dl._aria2c_enabled() is True
    assert any("CDN blocked aria2" in s for s in notes)

    n["i"] = 0

    def second(url: str, progress_cb=None):
        n["i"] += 1
        assert "--downloader" in dl._build_cli_cmd(url)
        path = tmp_path / "ok2.mp4"
        path.write_bytes(b"media")
        return DownloadResult(path=path, title="ok2", info={})

    dl._download_inprocess = second  # type: ignore[method-assign]
    dl.download("https://www.youtube.com/watch?v=y")
    assert n["i"] == 1
    assert dl.aria2_fallback_native is False
    assert dl.download_method == "aria2c"


def test_worker_does_not_fail_or_fail_pause_after_aria2_attempt_one(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("frameforge.download.invocation.aria2c_available", lambda: True)
    repo = JobRepository(tmp_path / "j.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=True)
    n = {"i": 0}

    def fake_inprocess(url: str, progress_cb=None):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError(ARIA2_403_STDERR)
        path = out / "ok.mp4"
        path.write_bytes(b"media")
        return DownloadResult(path=path, title="ok", info={})

    dl._download_inprocess = fake_inprocess  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    paused: list[int] = []
    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    worker.on_fail_pause = lambda job: paused.append(job.id)
    job = repo.enqueue("https://example.com/watch?v=x")
    worker.request_download_ids([job.id])
    import time

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert loaded.status == "completed"
    assert n["i"] == 2
    assert paused == []
    opts = loaded.options()
    assert opts.get("aria2_fallback_native") is True
    assert opts.get("download_attempt") == 2
    assert opts.get("download_method") == "native"
    cmd = opts["ytdlp_invocation"]["argv"]
    assert "--downloader" not in cmd
    worker.stop(timeout=5)
    repo.close()


def test_final_aria2_forbidden_does_not_fail_pause(tmp_path: Path):
    repo = JobRepository(tmp_path / "f.db")
    job = repo.enqueue("https://example.com/v")
    repo.update_status(job.id, "failed", error=ARIA2_403_STDERR)
    from frameforge.errors import annotate_job_error

    annotate_job_error(repo, job.id, ARIA2_403_STDERR)
    failed = repo.get(job.id)
    assert failed.options().get("error_category") == ARIA2_FORBIDDEN
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    assert maybe_fail_pause(worker, repo, failed) is False
    repo.close()


def test_worker_fails_only_after_native_also_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.invocation.aria2c_available", lambda: True)
    repo = JobRepository(tmp_path / "both.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=True)
    n = {"i": 0}

    def fake_inprocess(url: str, progress_cb=None):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError(ARIA2_403_STDERR)
        raise RuntimeError("native downloader also failed: Connection reset by peer")

    dl._download_inprocess = fake_inprocess  # type: ignore[method-assign]
    worker = SequentialWorker(
        repo, download_handler=make_download_handler(dl), poll_interval=0.02
    )
    job = repo.enqueue("https://example.com/watch?v=z")
    worker.request_download_ids([job.id])
    import time

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status in ("pending", "downloading"):
        time.sleep(0.02)
    loaded = repo.get(job.id)
    assert n["i"] == 2
    assert loaded.status == "failed"
    assert loaded.options().get("aria2_fallback_native") is True
    assert loaded.options().get("download_attempt") == 2
    assert classify_error(loaded.error) == NETWORK
    worker.stop(timeout=5)
    repo.close()
