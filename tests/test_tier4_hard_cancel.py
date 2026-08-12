"""Tier 4.1 — hard cancel kills yt-dlp/aria2c process tree; worker recovers."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker
from frameforge.util.process_tree import pid_is_running, popen_creationflags, wait_pid_gone

SAMPLE_10S = "https://samplelib.com/lib/preview/mp4/sample-10s.mp4"
SAMPLE_5S = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"


def test_cancel_non_active_job_only_updates_status(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    job = repo.enqueue("https://example.com/pending-only")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    done = worker.cancel_job(job.id)
    assert done.status == "cancelled"
    assert worker.processes.pid_for(job.id) is None
    repo.close()


def test_hard_cancel_kills_process_tree_and_allows_next_job(tmp_path: Path):
    """Real subprocess tree kill via the same registry the downloader uses."""
    import subprocess

    ensure_output_tree()
    repo = JobRepository(tmp_path / "k.db")
    seen: list[int] = []

    def long_handler(job, r):
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "creationflags": popen_creationflags(),
        }
        if sys.platform != "win32":
            kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "start_new_session": True}
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", "import time; time.sleep(120)"],
            **kwargs,
        )
        worker.processes.register(job.id, proc.pid)
        seen.append(proc.pid)
        try:
            while proc.poll() is None:
                if r.get(job.id).status == "cancelled":
                    raise RuntimeError("cancelled")
                time.sleep(0.05)
        finally:
            if proc.poll() is None:
                worker.processes.kill(job.id)
                try:
                    proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass
            worker.processes.unregister(job.id)

    worker = SequentialWorker(repo, download_handler=long_handler, poll_interval=0.02)
    j1 = repo.enqueue("https://example.com/slow")
    j2 = repo.enqueue(SAMPLE_5S, title="after")

    worker.request_download_ids([j1.id])
    deadline = time.time() + 15
    pid = None
    while time.time() < deadline:
        pid = worker.processes.pid_for(j1.id)
        if pid and repo.get(j1.id).status == "downloading":
            break
        time.sleep(0.05)
    assert pid is not None and pid_is_running(pid)

    worker.cancel_job(j1.id)
    assert wait_pid_gone(pid, timeout=15)
    # Wait for worker to finish handling cancel
    deadline = time.time() + 15
    while time.time() < deadline and repo.get(j1.id).status == "downloading":
        time.sleep(0.05)
    assert repo.get(j1.id).status == "cancelled"

    # Next job: use killable yt-dlp path and complete successfully
    out = tmp_path / "dl"
    out.mkdir()
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=True)
    worker.download_handler = make_download_handler(dl, process_registry=worker.processes)
    worker.request_download_ids([j2.id])
    deadline = time.time() + 180
    while time.time() < deadline:
        if repo.get(j2.id).status == "completed":
            break
        time.sleep(0.2)
    assert repo.get(j2.id).status == "completed", repo.get(j2.id).error
    assert repo.get(j2.id).download_path and Path(repo.get(j2.id).download_path).exists()
    worker.stop(timeout=5)
    repo.close()


@pytest.mark.timeout(180)
def test_hard_cancel_real_download_process_gone(tmp_path: Path):
    ensure_output_tree()
    out = tmp_path / "dl"
    out.mkdir()
    repo = JobRepository(tmp_path / "r.db")
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=True)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.02)
    worker.download_handler = make_download_handler(dl, process_registry=worker.processes)

    job = repo.enqueue(SAMPLE_10S)
    worker.request_download_ids([job.id])

    deadline = time.time() + 60
    pid = None
    while time.time() < deadline:
        st = repo.get(job.id).status
        pid = worker.processes.pid_for(job.id)
        if st == "downloading" and pid is not None:
            break
        if st in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.05)

    if repo.get(job.id).status == "completed":
        pytest.skip("download finished before cancel window; network too fast")
    assert pid is not None, "expected killable yt-dlp PID while downloading"
    assert pid_is_running(pid)

    worker.cancel_job(job.id)
    assert wait_pid_gone(pid, timeout=20)
    deadline = time.time() + 30
    while time.time() < deadline and repo.get(job.id).status == "downloading":
        time.sleep(0.05)
    assert repo.get(job.id).status == "cancelled", repo.get(job.id).error
    worker.stop(timeout=5)
    repo.close()
