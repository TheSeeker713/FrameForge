"""Step 1.3 — resume paused downloads with continue semantics."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker
from frameforge.util.process_tree import DownloadPaused

SAMPLE_5S = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"


def test_cli_continue_and_aria2c_resume_flags():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=True)
    cmd = dl._build_cli_cmd("https://example.com/v")
    joined = " ".join(cmd)
    assert "--continue" in cmd
    assert "remove-control-file" not in joined
    assert "--allow-overwrite=true" in joined
    assert "--auto-file-renaming=false" in joined
    opts = dl.build_opts()
    assert opts.get("continuedl") is True
    aria = " ".join(opts["external_downloader_args"]["aria2c"])
    assert "remove-control-file" not in aria
    assert "--allow-overwrite=true" in aria


def test_resume_paused_completes_and_keeps_sequential(tmp_path: Path):
    repo = JobRepository(tmp_path / "r.db")
    out = tmp_path / "dl"
    out.mkdir()
    part = out / "clip.mp4.part"
    calls = {"n": 0}
    max_downloading = {"n": 0}

    def handler(job, r):
        n_dl = r.count_by_status("downloading")
        max_downloading["n"] = max(max_downloading["n"], n_dl)
        calls["n"] += 1
        r.merge_options(job.id, {"download_output_dir": str(out)})
        if calls["n"] == 1:
            part.write_bytes(b"partial")
            r.set_paths(job.id, download_path=str(part))
            r.update_progress(job.id, 25)
            while r.get(job.id).status == "downloading":
                time.sleep(0.02)
            raise DownloadPaused("paused")
        assert part.exists(), "resume must see preserved partial"
        final = out / "clip.mp4"
        final.write_bytes(part.read_bytes() + b"-done")
        r.set_paths(job.id, download_path=str(final), output_path=str(final))
        r.update_progress(job.id, 100)

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    job = repo.enqueue("https://example.com/resume-me")
    other = repo.enqueue("https://example.com/later")
    worker.request_download_ids([job.id])

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status != "downloading":
        time.sleep(0.02)
    assert repo.get(job.id).status == "downloading"

    worker.pause_job(job.id)
    deadline = time.time() + 10
    while time.time() < deadline and repo.get(job.id).status == "downloading":
        time.sleep(0.02)
    assert repo.get(job.id).status == "paused"
    assert part.exists()
    assert repo.get(other.id).status == "pending"
    assert not worker.is_armed

    worker.resume_job(job.id)
    deadline = time.time() + 15
    while time.time() < deadline:
        if repo.get(job.id).status == "completed":
            break
        time.sleep(0.05)
    loaded = repo.get(job.id)
    assert loaded.status == "completed", loaded.error
    assert loaded.download_path and Path(loaded.download_path).exists()
    assert repo.get(other.id).status == "pending"
    assert max_downloading["n"] <= 1
    assert repo.count_by_status("downloading") == 0
    worker.stop(timeout=5)
    repo.close()


def test_resume_paused_upscale_returns_to_chain(tmp_path: Path):
    repo = JobRepository(tmp_path / "u.db")
    job = repo.enqueue("https://example.com/u")
    repo.claim_next_pending()
    repo.update_status(job.id, "upscaling")
    repo.pause(job.id)
    resumed = repo.resume_paused(job.id)
    assert resumed.status == "download_completed"
    assert resumed.upscale is True
    repo.close()


@pytest.mark.timeout(180)
def test_resume_real_short_clip_completes(tmp_path: Path):
    ensure_output_tree()
    out = tmp_path / "dl"
    out.mkdir()
    repo = JobRepository(tmp_path / "net.db")
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=True)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.02)
    worker.download_handler = make_download_handler(dl, process_registry=worker.processes)
    job = repo.enqueue(SAMPLE_5S)
    worker.request_download_ids([job.id])

    deadline = time.time() + 60
    while time.time() < deadline:
        st = repo.get(job.id).status
        if st == "downloading" and worker.processes.pid_for(job.id):
            break
        if st in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)

    st = repo.get(job.id).status
    if st == "completed":
        worker.stop(timeout=5)
        repo.close()
        pytest.skip("clip finished before pause window")
    if st != "downloading":
        worker.stop(timeout=5)
        repo.close()
        pytest.fail(f"expected downloading, got {st}: {repo.get(job.id).error}")

    worker.pause_job(job.id)
    deadline = time.time() + 30
    while time.time() < deadline and repo.get(job.id).status == "downloading":
        time.sleep(0.05)
    assert repo.get(job.id).status == "paused", repo.get(job.id).error

    worker.resume_job(job.id)
    deadline = time.time() + 180
    while time.time() < deadline:
        if repo.get(job.id).status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.2)
    loaded = repo.get(job.id)
    assert loaded.status == "completed", loaded.error
    assert loaded.download_path and Path(loaded.download_path).exists()
    worker.stop(timeout=5)
    repo.close()
