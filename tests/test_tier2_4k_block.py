"""Tier 2.2 — block upscale when source height ≥ 2160 (4K)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.paths import ensure_output_tree, models_dir
from frameforge.queue.worker import SequentialWorker
from frameforge.upscale.guards import UpscaleBlockedError, assert_upscale_allowed
from frameforge.upscale.handler import make_upscale_handler
from frameforge.upscale.pipeline import UpscalePipeline


def _make_clip(path: Path, *, size: str, seconds: float = 0.4) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=5:duration={seconds}",
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


def test_assert_blocks_2160_and_allows_1080(tmp_path: Path):
    low = _make_clip(tmp_path / "hd.mp4", size="1280x720")
    w, h = assert_upscale_allowed(low)
    assert h < 2160
    assert w == 1280

    uhd = _make_clip(tmp_path / "uhd.mp4", size="3840x2160")
    with pytest.raises(UpscaleBlockedError, match=r"height=2160"):
        assert_upscale_allowed(uhd)


def test_pipeline_blocks_4k(tmp_path: Path):
    ensure_output_tree()
    uhd = _make_clip(tmp_path / "uhd2.mp4", size="3840x2160")
    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=tmp_path / "w",
        max_frames=2,
        tile=64,
    )
    with pytest.raises(UpscaleBlockedError, match="4K"):
        pipe.run(uhd, job_key="blocked", output_path=tmp_path / "out.mp4")


def test_worker_marks_failed_with_block_reason(tmp_path: Path):
    ensure_output_tree()
    uhd = _make_clip(tmp_path / "uhd3.mp4", size="3840x2160")
    repo = JobRepository(tmp_path / "b.db")
    job = repo.enqueue("https://example.com/4k", title="4k-clip")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(uhd), output_path=str(uhd))

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
    repo.queue_for_upscale(job.id)
    with worker._lock:
        worker._only_ids = set()
        worker._armed.set()
    worker._process_one()
    done = repo.get(job.id)
    assert done.status == "failed"
    assert done.error is not None
    assert "2160" in done.error
    assert "Blocked" in done.error
    # Model/UI exposure: error field is what queue list shows
    assert "4K" in done.error or "≥2160" in done.error or "2160" in done.error
    worker.disarm()
    repo.close()


def test_below_2160_still_upscales(tmp_path: Path):
    ensure_output_tree()
    clip = _make_clip(tmp_path / "ok.mp4", size="640x360")
    repo = JobRepository(tmp_path / "ok.db")
    job = repo.enqueue("https://example.com/ok", title="ok")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
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
    repo.queue_for_upscale(job.id)
    with worker._lock:
        worker._only_ids = set()
        worker._armed.set()
    worker._process_one()
    done = repo.get(job.id)
    assert done.status == "completed", done.error
    assert done.output_path and Path(done.output_path).exists()
    worker.disarm()
    repo.close()
