"""Tier 2.1 — upscale selected completed downloads (2×)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from frameforge.db.repository import Job, JobRepository
from frameforge.paths import ensure_output_tree, models_dir
from frameforge.queue.worker import SequentialWorker
from frameforge.upscale.handler import make_upscale_handler
from frameforge.upscale.pipeline import UpscalePipeline


def _make_clip(path: Path, *, size: str = "64x48", seconds: float = 0.6) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=8:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
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


def _pipe(tmp_path: Path, max_frames: int = 4) -> UpscalePipeline:
    return UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=tmp_path / "work",
        max_frames=max_frames,
        tile=64,
    )


def test_queue_for_upscale_requires_completed_with_file(tmp_path: Path):
    repo = JobRepository(tmp_path / "q.db")
    pending = repo.enqueue("https://example.com/a")
    with pytest.raises(ValueError, match="completed"):
        repo.queue_for_upscale(pending.id)

    job = repo.enqueue("https://example.com/b")
    repo.update_status(job.id, "completed", progress=100)
    with pytest.raises(ValueError, match="download_path"):
        repo.queue_for_upscale(job.id)

    clip = _make_clip(tmp_path / "src.mp4")
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
    queued = repo.queue_for_upscale(job.id)
    assert queued.status == "download_completed"
    assert queued.upscale is True
    assert queued.progress == 0.0
    repo.close()


@pytest.mark.timeout(180)
def test_upscale_selected_produces_output(tmp_path: Path):
    ensure_output_tree()
    clip = _make_clip(tmp_path / "done.mp4")
    repo = JobRepository(tmp_path / "up.db")
    job = repo.enqueue("https://example.com/local", title="local-clip")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))

    worker = SequentialWorker(
        repo,
        download_handler=lambda j, r: None,
        upscale_handler=make_upscale_handler(_pipe(tmp_path)),
        poll_interval=0.05,
    )
    # Synchronous path: queue then process one stage in this thread
    queued_ids = []
    repo.queue_for_upscale(job.id)
    queued_ids.append(job.id)
    with worker._lock:
        worker._only_ids = set()
        worker._armed.set()
    assert worker._process_one() is True
    done = repo.get(job.id)
    # May still be upscaling mid-handler if _process_one runs full upscale — it should finish
    assert done.status == "completed", done.error
    assert done.output_path and Path(done.output_path).exists()
    assert Path(done.output_path).stat().st_size > 0
    worker.disarm()
    repo.close()


@pytest.mark.timeout(180)
def test_upscale_selected_sequential_with_pending_download(tmp_path: Path):
    """Upscale-only arm must not claim pending downloads."""
    ensure_output_tree()
    clip = _make_clip(tmp_path / "a.mp4")
    repo = JobRepository(tmp_path / "seq.db")
    completed = repo.enqueue("https://example.com/done", title="done")
    repo.update_status(completed.id, "completed", progress=100)
    repo.set_paths(completed.id, download_path=str(clip), output_path=str(clip))
    pending = repo.enqueue("https://example.com/pending", title="pending")

    downloaded: list[int] = []

    def dl(job: Job, r: JobRepository) -> None:
        downloaded.append(job.id)
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    worker = SequentialWorker(
        repo,
        download_handler=dl,
        upscale_handler=make_upscale_handler(_pipe(tmp_path, max_frames=3)),
        poll_interval=0.05,
    )
    worker.request_upscale_ids([completed.id], start_loop=False)
    assert worker.is_running is False
    # Single-thread drain: never call _process_one while the background loop is alive
    # (ORT/DirectML access-violates if two sessions run in one process).
    deadline = time.time() + 120
    while time.time() < deadline:
        if repo.get(completed.id).status in ("completed", "failed"):
            break
        if worker.is_armed:
            worker._process_one()
        else:
            time.sleep(0.05)
    worker.disarm()
    assert repo.get(completed.id).status == "completed", repo.get(completed.id).error
    assert repo.get(pending.id).status == "pending"
    assert downloaded == []
    repo.close()


def test_request_upscale_rejects_non_completed(tmp_path: Path):
    repo = JobRepository(tmp_path / "rej.db")
    job = repo.enqueue("https://example.com/x")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None)
    with pytest.raises(ValueError):
        worker.request_upscale_ids([job.id], start_loop=False)
    assert worker.is_running is False
    worker.stop()
    repo.close()
