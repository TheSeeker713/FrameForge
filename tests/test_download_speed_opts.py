"""Step 4.1 — sequential downloads still use aria2c multi-connection speed flags."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.ytdlp import YtDlpDownloader


def test_aria2c_opts_include_speed_flags():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=True)
    opts = dl.build_opts()
    assert opts["format"] == "bv*+ba/b"
    assert opts["continuedl"] is True
    assert opts["external_downloader"]["default"] == "aria2c"
    args = opts["external_downloader_args"]["aria2c"]
    joined = " ".join(args)
    assert "-x" in args and "8" in args
    assert "-s" in args
    assert "-k" in args
    assert "-c" in args
    assert "--allow-overwrite=true" in joined
    cmd = dl._build_cli_cmd("https://example.com/v")
    cli = " ".join(cmd)
    assert "--downloader" in cmd
    assert "aria2c" in cli
    assert "-x 8" in cli
    assert "-f" in cmd
    assert "bv*+ba/b" in cmd


def test_native_path_uses_concurrent_fragments():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    opts = dl.build_opts()
    assert "external_downloader" not in opts
    assert opts["concurrent_fragment_downloads"] == 8
    assert opts["format"] == "bv*+ba/b"


def test_gentle_rate_mode_adds_sleep_and_limit():
    from frameforge.download.ytdlp import apply_gentle_rate

    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=True)
    apply_gentle_rate(dl, True)
    opts = dl.build_opts()
    assert opts["sleep_interval"] == 2.0
    assert opts["ratelimit"] == 2 * 1024 * 1024
    cmd = " ".join(dl._build_cli_cmd("https://example.com/v"))
    assert "--sleep-interval" in cmd
    assert "--limit-rate" in cmd
    apply_gentle_rate(dl, False)
    opts2 = dl.build_opts()
    assert "sleep_interval" not in opts2
    assert "ratelimit" not in opts2


def test_handler_applies_gentle_rate_from_setting(tmp_path: Path):
    from frameforge.db.repository import JobRepository
    from frameforge.download.handler import make_download_handler
    from frameforge.download.ytdlp import DownloadResult

    repo = JobRepository(tmp_path / "jobs.db")
    repo.set_setting("gentle_rate_mode", "1")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "archive.txt")
    captured: dict[str, float | int | None] = {}

    def fake_download(url: str, **kwargs: object):
        captured["sleep"] = dl.sleep_interval
        captured["limit"] = dl.limit_rate_bps
        path = out / "x.mp4"
        path.write_bytes(b"not-a-real-video")
        return DownloadResult(path=path, title="t", info={})

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/watch?v=abc")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    assert captured["sleep"] == 2.0
    assert captured["limit"] == 2 * 1024 * 1024
    repo.close()


def test_handler_leaves_fast_path_when_gentle_rate_off(tmp_path: Path):
    from frameforge.db.repository import JobRepository
    from frameforge.download.handler import make_download_handler
    from frameforge.download.ytdlp import DownloadResult

    repo = JobRepository(tmp_path / "jobs.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "archive.txt")
    captured: dict[str, float | int | None] = {}

    def fake_download(url: str, **kwargs: object):
        captured["sleep"] = dl.sleep_interval
        captured["limit"] = dl.limit_rate_bps
        path = out / "x.mp4"
        path.write_bytes(b"not-a-real-video")
        return DownloadResult(path=path, title="t", info={})

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/watch?v=abc")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    assert captured["sleep"] is None
    assert captured["limit"] is None
    repo.close()
