"""Step 3 — new downloads land in per-site folders; resume keeps the same path."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import resolve_download_output_dir
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import download_dir_for_site, frameforge_root


def test_youtube_job_dir_and_opts_contain_youtube(tmp_path: Path):
    repo = JobRepository(tmp_path / "yt.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc123")
    dest = resolve_download_output_dir(job)
    assert dest == download_dir_for_site("youtube")
    assert dest.name == "youtube"
    assert dest.parent == frameforge_root()
    assert dest.is_dir()
    dl = YtDlpDownloader(output_dir=dest)
    opts = dl.build_opts()
    assert "youtube" in str(opts["outtmpl"]).replace("\\", "/")
    repo.close()


def test_x_com_job_dir_contains_x_com(tmp_path: Path):
    repo = JobRepository(tmp_path / "x.db")
    job = repo.enqueue("https://x.com/user/status/99")
    dest = resolve_download_output_dir(job)
    assert dest.name == "x.com"
    assert "x.com" in dest.parts
    dl = YtDlpDownloader(output_dir=dest)
    assert "x.com" in str(dl.build_opts()["outtmpl"]).replace("\\", "/")
    repo.close()


def test_resume_keeps_existing_download_output_dir(tmp_path: Path):
    repo = JobRepository(tmp_path / "r.db")
    prior = tmp_path / "already-there"
    prior.mkdir()
    job = repo.enqueue("https://www.youtube.com/watch?v=resume")
    repo.merge_options(job.id, {"download_output_dir": str(prior)})
    dest = resolve_download_output_dir(repo.get(job.id))
    assert dest == prior
    repo.close()


def test_sequential_claim_untouched(tmp_path: Path):
    repo = JobRepository(tmp_path / "seq.db")
    repo.enqueue("https://www.youtube.com/watch?v=1")
    repo.enqueue("https://x.com/a/status/2")
    a = repo.claim_next_pending()
    b = repo.claim_next_pending()
    assert a is not None
    assert b is None
    assert repo.count_by_status("downloading") == 1
    repo.close()
