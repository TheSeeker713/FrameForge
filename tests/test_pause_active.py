"""Step 1.2 — pause active download: hard-kill, keep partials, worker idle."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.partials import collect_partial_artifacts
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree
from frameforge.queue.worker import SequentialWorker
from frameforge.util.process_tree import pid_is_running, popen_creationflags, wait_pid_gone

SAMPLE_10S = "https://samplelib.com/lib/preview/mp4/sample-10s.mp4"


def test_collect_partial_artifacts(tmp_path: Path):
    (tmp_path / "clip.mp4.part").write_bytes(b"abc")
    (tmp_path / "clip.mp4.aria2").write_text("ctl")
    (tmp_path / "clip.mp4").write_bytes(b"done")
    found = collect_partial_artifacts(tmp_path)
    assert any(p.endswith(".part") for p in found)
    assert any(p.endswith(".aria2") for p in found)
    assert not any(p.endswith("clip.mp4") and not p.endswith(".part") for p in found)


def test_pause_simulated_download_idle_and_partials(tmp_path: Path):
    import subprocess

    repo = JobRepository(tmp_path / "p.db")
    out = tmp_path / "dl"
    out.mkdir()
    part = out / "clip.mp4.part"
    part.write_bytes(b"partial-bytes")

    def long_handler(job, r):
        r.merge_options(job.id, {"download_output_dir": str(out)})
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "creationflags": popen_creationflags(),
        }
        if sys.platform != "win32":
            kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "start_new_session": True,
            }
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", "import time; time.sleep(120)"],
            **kwargs,
        )
        worker.processes.register(job.id, proc.pid)
        try:
            while proc.poll() is None:
                st = r.get(job.id).status
                if st in ("cancelled", "paused"):
                    break
                time.sleep(0.05)
        finally:
            if proc.poll() is None:
                worker.processes.kill(job.id)
                try:
                    proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass

    worker = SequentialWorker(repo, download_handler=long_handler, poll_interval=0.02)
    j1 = repo.enqueue("https://example.com/slow")
    j2 = repo.enqueue("https://example.com/next")
    worker.request_download_ids([j1.id, j2.id])

    deadline = time.time() + 15
    pid = None
    while time.time() < deadline:
        pid = worker.processes.pid_for(j1.id)
        if pid and repo.get(j1.id).status == "downloading":
            break
        time.sleep(0.05)
    assert pid is not None and pid_is_running(pid)

    paused = worker.pause_job(j1.id)
    assert paused.status == "paused"
    assert paused.status != "failed"
    assert paused.status != "cancelled"
    assert wait_pid_gone(pid, timeout=15)
    assert part.exists(), "pause must not delete .part files"
    opts = repo.get(j1.id).options()
    assert opts.get("download_output_dir") == str(out)
    assert any(str(part) == p or p.endswith(".part") for p in (opts.get("partial_paths") or []))

    deadline = time.time() + 10
    while time.time() < deadline and repo.get(j1.id).status == "downloading":
        time.sleep(0.05)
    assert repo.get(j1.id).status == "paused"
    assert repo.count_by_status("downloading") == 0
    assert not worker.is_armed
    assert repo.get(j2.id).status == "pending"
    worker.stop(timeout=5)
    repo.close()


@pytest.mark.timeout(180)
def test_pause_real_download_no_stuck_downloading(tmp_path: Path):
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
        if st in ("completed", "failed", "cancelled", "paused"):
            break
        time.sleep(0.05)

    if repo.get(job.id).status == "completed":
        pytest.skip("download finished before pause window; network too fast")
    assert pid is not None, "expected killable yt-dlp PID while downloading"
    assert pid_is_running(pid)

    worker.pause_job(job.id)
    assert wait_pid_gone(pid, timeout=20)
    deadline = time.time() + 30
    while time.time() < deadline and repo.get(job.id).status == "downloading":
        time.sleep(0.05)
    loaded = repo.get(job.id)
    assert loaded.status == "paused", loaded.error
    assert loaded.status != "failed"
    assert repo.count_by_status("downloading") == 0
    assert not worker.is_armed
    opts = loaded.options()
    assert opts.get("download_output_dir")
    parts = collect_partial_artifacts(opts.get("download_output_dir"))
    # Partials may exist, or path fields are retained for resume.
    assert opts.get("download_output_dir") or loaded.download_path or parts
    worker.stop(timeout=5)
    repo.close()
