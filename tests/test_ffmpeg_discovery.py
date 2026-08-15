"""Resolve ffmpeg from PATH and WinGet Gyan locations; pass --ffmpeg-location."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.invocation import ffmpeg_location, snapshot_invocation
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.error_report import format_full_error_report


def test_ffmpeg_discovers_winget_gyan(tmp_path: Path, monkeypatch):
    local = tmp_path / "AppData" / "Local"
    pkg = local / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg_Gyan.FFmpeg__abc"
    bindir = pkg / "ffmpeg-7.1-full_build" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / "ffmpeg.exe"
    exe.write_bytes(b"mz")
    (bindir / "ffprobe.exe").write_bytes(b"mz")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr("frameforge.download.invocation.shutil.which", lambda _n: None)
    found = ffmpeg_location()
    assert found is not None
    assert Path(found) == exe.resolve()


def test_cli_passes_ffmpeg_location_when_outside_path(tmp_path: Path, monkeypatch):
    fake = tmp_path / "gyan" / "bin" / "ffmpeg.exe"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"mz")
    monkeypatch.setattr("frameforge.download.invocation.ffmpeg_location", lambda: str(fake.resolve()))
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    cmd = dl._build_cli_cmd("https://example.com/v")
    assert "--ffmpeg-location" in cmd
    loc = cmd[cmd.index("--ffmpeg-location") + 1]
    assert Path(loc) == fake.parent.resolve() or loc == str(fake.parent)


def test_error_report_logs_ffmpeg_path(tmp_path: Path):
    from frameforge.db.repository import JobRepository
    from frameforge.errors import annotate_job_error

    repo = JobRepository(tmp_path / "e.db")
    job = repo.enqueue("https://example.com/v")
    annotate_job_error(repo, job.id, "ffmpeg failed: No such file or directory")
    snap = snapshot_invocation(
        argv=["python", "-m", "yt_dlp"],
        cwd=str(tmp_path),
        output_template="x",
        cookies=None,
        aria2c=False,
        format_selector="bv*+ba/b",
        ffmpeg=r"C:\Users\me\WinGet\ffmpeg.exe",
    )
    repo.merge_options(job.id, {"ytdlp_invocation": snap})
    text = format_full_error_report(repo.get(job.id))
    assert "ffmpeg_location:" in text
    assert "WinGet" in text or "ffmpeg.exe" in text
    repo.close()
