"""yt-dlp CLI parity: argv, cookies, aria2c, cwd, empty-stderr reporting."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.invocation import argv_summary, bundled_yt_dlp_version, snapshot_invocation
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.errors import format_ytdlp_exit_error


def test_describe_cli_invocation_matches_build_cmd(tmp_path: Path):
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    url = "https://example.com/watch?v=abc"
    snap = dl.describe_cli_invocation(url)
    cmd = dl._build_cli_cmd(url)
    assert snap["argv"] == cmd
    assert snap["cwd"] == str(out)
    assert snap["cookies"] is None
    assert "--cookies" not in cmd
    assert snap["format"] == "bv*+ba/b"
    assert snap["yt_dlp_version"] == bundled_yt_dlp_version()
    assert snap["python"]
    assert url in cmd
    assert cmd[0]
    assert cmd[-1] == url


def test_empty_cookie_stub_not_passed(tmp_path: Path):
    stub = tmp_path / "youtube.txt"
    stub.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    dl = YtDlpDownloader(
        output_dir=tmp_path / "o",
        archive_file=tmp_path / "a.txt",
        use_aria2c=False,
        cookiefile=stub,
    )
    cmd = dl._build_cli_cmd("https://www.youtube.com/watch?v=x")
    assert "--cookies" not in cmd
    assert "cookiefile" not in dl.build_opts()


def test_handler_clears_sticky_cookiefile(tmp_path: Path, monkeypatch):
    repo = JobRepository(tmp_path / "jobs.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)
    cookie = tmp_path / "site.txt"
    cookie.write_text("# Netscape\n.site.test\tTRUE\t/\tFALSE\t0\ta\tb\n", encoding="utf-8")
    seen: list[object] = []

    def fake_download(url: str, **kwargs: object):
        seen.append(dl.cookiefile)
        path = out / "x.mp4"
        path.write_bytes(b"not-a-real-video")
        return DownloadResult(path=path, title="t", info={})

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)

    def fake_cookie(url: str):
        if "first" in url:
            return cookie
        return None

    monkeypatch.setattr("frameforge.download.handler._cookiefile_for_url", fake_cookie)
    j1 = repo.enqueue("https://example.com/first")
    j2 = repo.enqueue("https://example.com/second")
    repo.update_status(j1.id, "downloading")
    handler(j1, repo)
    repo.update_status(j2.id, "downloading")
    handler(j2, repo)
    assert seen[0] == cookie
    assert seen[1] is None
    inv = repo.get(j2.id).options().get("ytdlp_invocation")
    assert inv and inv.get("argv")
    repo.close()


def test_aria2c_omitted_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("frameforge.download.invocation.shutil.which", lambda _n: None)
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=True)
    cmd = dl._build_cli_cmd("https://example.com/v")
    assert "--downloader" not in cmd
    opts = dl.build_opts()
    assert "external_downloader" not in opts
    assert opts.get("concurrent_fragment_downloads") == 8


def test_empty_stderr_includes_argv_and_hint():
    argv = [r"C:\Python\python.exe", "-m", "yt_dlp", "https://example.com/v"]
    msg = format_ytdlp_exit_error(1, [], argv=argv)
    assert "no stderr; see invocation log" in msg
    assert "argv:" in msg
    assert "yt_dlp" in msg
    snap = snapshot_invocation(
        argv=argv,
        cwd="D:\\out",
        output_template="%(title)s",
        cookies=None,
        aria2c=False,
        format_selector="bv*+ba/b",
        returncode=1,
        stderr_empty=True,
    )
    assert argv_summary(snap["argv"])
    assert snap["stderr_empty"] is True


def test_handler_stores_invocation_snapshot(tmp_path: Path):
    repo = JobRepository(tmp_path / "jobs.db")
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)

    def fake_download(url: str, **kwargs: object):
        dl.describe_cli_invocation(url)
        path = out / "x.mp4"
        path.write_bytes(b"not-a-real-video")
        return DownloadResult(path=path, title="t", info={})

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/watch?v=abc")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    inv = repo.get(job.id).options()["ytdlp_invocation"]
    assert inv["argv"][-1] == job.url
    assert inv["cwd"] == str(out)
    assert inv["cookies"] is None
    repo.close()
