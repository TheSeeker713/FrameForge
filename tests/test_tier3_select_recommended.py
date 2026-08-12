"""Tier 3.3 — select recommended + upscale wiring; 4K still blocked."""

from __future__ import annotations

import subprocess
from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.queue_list import QueueList
from frameforge.paths import ensure_output_tree, models_dir
from frameforge.queue.worker import SequentialWorker
from frameforge.upscale.handler import make_upscale_handler
from frameforge.upscale.pipeline import UpscalePipeline


def _clip(path: Path, size: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=5:duration=0.4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return path


def _sync_upscale(repo: JobRepository, worker: SequentialWorker, job_id: int) -> None:
    """Run one upscale stage on the calling thread (no background worker race)."""
    with worker._lock:
        worker._only_ids = set()
        worker._armed.set()
    worker._process_one()
    worker.disarm()


def test_select_recommended_ids(tmp_path: Path):
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "s.db")
        a = repo.enqueue("https://example.com/a")
        b = repo.enqueue("https://example.com/b")
        c = repo.enqueue("https://example.com/c")
        for j in (a, b, c):
            repo.update_status(j.id, "completed", progress=100)
        repo.set_source_resolution(a.id, 640, 360)
        repo.set_source_resolution(b.id, 1920, 1080)
        repo.set_source_resolution(c.id, 1280, 720)
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        recommended = ql.recommended_ids
        assert recommended == {a.id, c.id}
        ql.set_selected(recommended)
        assert ql.selected_ids == {a.id, c.id}
        repo.close()
    finally:
        root.destroy()


def test_recommended_job_can_queue_upscale(tmp_path: Path):
    ensure_output_tree()
    clip = _clip(tmp_path / "sd.mp4", "640x360")
    repo = JobRepository(tmp_path / "u.db")
    job = repo.enqueue("https://example.com/sd", title="sd")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
    repo.probe_and_store_resolution(job.id)
    assert repo.get(job.id).upscale_recommended is True

    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=tmp_path / "w",
        max_frames=3,
        tile=64,
    )
    worker = SequentialWorker(
        repo,
        download_handler=lambda j, r: None,
        upscale_handler=make_upscale_handler(pipe),
    )
    # Queue via public API then stop background thread before sync upscale
    queued = worker.request_upscale_ids([job.id])
    assert queued == [job.id]
    assert repo.get(job.id).status == "download_completed"
    worker.stop(timeout=5)
    _sync_upscale(repo, worker, job.id)
    done = repo.get(job.id)
    assert done.status == "completed", done.error
    assert done.output_path and Path(done.output_path).exists()
    repo.close()


def test_blocked_4k_still_refuses_upscale(tmp_path: Path):
    ensure_output_tree()
    clip = _clip(tmp_path / "uhd.mp4", "3840x2160")
    repo = JobRepository(tmp_path / "b.db")
    job = repo.enqueue("https://example.com/uhd", title="uhd")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
    repo.probe_and_store_resolution(job.id)
    assert repo.get(job.id).upscale_blocked is True
    assert repo.get(job.id).upscale_recommended is False

    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=tmp_path / "w",
        max_frames=2,
        tile=64,
    )
    worker = SequentialWorker(
        repo,
        download_handler=lambda j, r: None,
        upscale_handler=make_upscale_handler(pipe),
    )
    worker.request_upscale_ids([job.id])
    worker.stop(timeout=5)
    _sync_upscale(repo, worker, job.id)
    done = repo.get(job.id)
    assert done.status == "failed"
    assert done.error and "2160" in done.error
    repo.close()
