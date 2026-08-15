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
    assert "-x" in args and "16" in args
    assert "-s" in args
    assert "-k" in args
    assert "-c" in args
    assert "--allow-overwrite=true" in joined
    cmd = dl._build_cli_cmd("https://example.com/v")
    cli = " ".join(cmd)
    assert "--downloader" in cmd
    assert "aria2c" in cli
    assert "-x 16" in cli
    assert "--concurrent-fragments" in cmd
    assert int(cmd[cmd.index("--concurrent-fragments") + 1]) >= 4
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


def test_max_download_rate_applied_when_gentle_off(tmp_path: Path):
    from frameforge.db.repository import JobRepository
    from frameforge.download.handler import make_download_handler
    from frameforge.download.throughput import parse_rate_bps
    from frameforge.download.ytdlp import DownloadResult

    assert parse_rate_bps("0") is None
    assert parse_rate_bps("2M") == 2 * 1024 * 1024
    assert parse_rate_bps("50K") == 50 * 1024

    repo = JobRepository(tmp_path / "jobs.db")
    repo.set_setting("max_download_rate", "2M")
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
    assert captured["limit"] == 2 * 1024 * 1024
    repo.close()


def _flag_value(cmd: list[str], flag: str) -> str | None:
    if flag not in cmd:
        return None
    return cmd[cmd.index(flag) + 1]


def test_youtube_default_speed_profile_has_fragments_no_limit_rate():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    cmd = dl._build_cli_cmd(url)
    n = int(_flag_value(cmd, "--concurrent-fragments") or "0")
    assert n >= 4
    assert "--limit-rate" not in cmd
    assert _flag_value(cmd, "--throttled-rate") == "100K"
    assert _flag_value(cmd, "--http-chunk-size") == "10M"
    opts = dl.build_opts(url=url)
    assert opts["concurrent_fragment_downloads"] >= 4
    assert "ratelimit" not in opts
    snap = dl.describe_cli_invocation(url)
    assert snap["cookies_attached"] is False
    assert snap["concurrent_fragments"] >= 4
    assert snap["throttled_rate"] == "100K"
    assert snap["player_client"]
    assert "player_client" in str(snap["player_client"])


def test_cookiefile_attached_logged(tmp_path: Path, caplog):
    import logging

    cookie = tmp_path / "youtube.txt"
    cookie.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc\n",
        encoding="utf-8",
    )
    dl = YtDlpDownloader(
        output_dir=tmp_path / "o",
        archive_file=tmp_path / "a.txt",
        use_aria2c=False,
        cookiefile=cookie,
    )
    with caplog.at_level(logging.INFO, logger="frameforge.download.ytdlp"):
        snap = dl.describe_cli_invocation("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert snap["cookies_attached"] is True
    assert snap["cookies"] == str(cookie)
    cmd = snap["argv"]
    assert "--cookies" in cmd
    assert str(cookie) in cmd
    assert "cookiefile attached" in caplog.text


def test_settings_override_concurrent_fragments(tmp_path: Path):
    from frameforge.db.repository import JobRepository
    from frameforge.download.throughput import concurrent_fragments

    repo = JobRepository(tmp_path / "s.db")
    assert concurrent_fragments(None) >= 4
    repo.set_setting("concurrent_fragments", "4")
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    dl._settings_repo = repo
    cmd = dl._build_cli_cmd("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert _flag_value(cmd, "--concurrent-fragments") == "4"
    repo.close()
