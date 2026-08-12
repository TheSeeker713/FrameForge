"""Step 3.2 — convert selected enqueue + sequential convert stage."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from frameforge.convert.handler import make_convert_handler
from frameforge.db.repository import Job, JobRepository
from frameforge.gui.actions import can_convert
from frameforge.paths import converted_dir_for_site, ensure_output_tree
from frameforge.queue.worker import SequentialWorker


def _make_clip(path: Path, *, seconds: float = 0.5) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=48x32:rate=8:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:duration={seconds}",
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


def test_convert_eligibility_and_ineligible_raises(tmp_path: Path):
    repo = JobRepository(tmp_path / "e.db")
    pending = repo.enqueue("https://example.com/p")
    assert can_convert(pending) is False
    with pytest.raises(ValueError, match="completed"):
        repo.queue_for_convert(pending.id)

    job = repo.enqueue("https://example.com/c")
    repo.update_status(job.id, "completed", progress=100)
    assert can_convert(repo.get(job.id)) is False
    with pytest.raises(ValueError, match="local media"):
        repo.queue_for_convert(job.id)

    clip = _make_clip(tmp_path / "ok.mp4")
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
    loaded = repo.get(job.id)
    assert can_convert(loaded) is True
    queued = repo.queue_for_convert(job.id)
    assert queued.status == "convert_pending"
    repo.close()


def test_converting_blocks_download_claim(tmp_path: Path):
    repo = JobRepository(tmp_path / "busy.db")
    clip = _make_clip(tmp_path / "a.mp4")
    conv = repo.enqueue("https://example.com/conv")
    repo.update_status(conv.id, "completed", progress=100)
    repo.set_paths(conv.id, download_path=str(clip), output_path=str(clip))
    repo.queue_for_convert(conv.id)
    claimed = repo.claim_next_convert()
    assert claimed is not None
    assert claimed.status == "converting"

    other = repo.enqueue("https://example.com/dl")
    assert repo.claim_next_pending() is None
    assert repo.get(other.id).status == "pending"
    repo.close()


def test_sequential_convert_after_download_no_overlap(tmp_path: Path):
    ensure_output_tree()
    repo = JobRepository(tmp_path / "seq.db")
    clip = _make_clip(tmp_path / "src.mp4")
    windows: list[tuple[str, float, float]] = []

    def download_handler(job: Job, r: JobRepository) -> None:
        start = time.time()
        time.sleep(0.08)
        r.set_paths(job.id, download_path=str(clip), output_path=str(clip))
        windows.append(("download", start, time.time()))

    worker = SequentialWorker(repo, download_handler=download_handler, poll_interval=0.02)
    inner = make_convert_handler(process_registry=worker.processes)

    def timed(job: Job, r: JobRepository) -> None:
        start = time.time()
        inner(job, r)
        windows.append(("convert", start, time.time()))

    worker.convert_handler = timed

    job = repo.enqueue("https://example.com/one")
    worker.request_download_ids([job.id])
    deadline = time.time() + 15
    while time.time() < deadline and repo.get(job.id).status != "completed":
        time.sleep(0.05)
    assert repo.get(job.id).status == "completed"

    worker.request_convert_ids([job.id], start_loop=True)
    deadline = time.time() + 30
    while time.time() < deadline:
        if repo.get(job.id).status == "completed" and repo.get(job.id).options().get("convert_path"):
            break
        time.sleep(0.05)
    loaded = repo.get(job.id)
    assert loaded.status == "completed", loaded.error
    convert_path = Path(loaded.options()["convert_path"])
    assert convert_path.is_file()
    assert convert_path.stat().st_size > 0
    assert convert_path.parent == converted_dir_for_site("example.com")

    kinds = [w[0] for w in windows]
    assert "download" in kinds
    assert "convert" in kinds
    # Non-overlapping stages
    for i in range(len(windows) - 1):
        assert windows[i][2] <= windows[i + 1][1] + 1e-3
    assert repo.count_by_status("downloading") == 0
    assert repo.count_by_status("converting") == 0
    worker.stop(timeout=5)
    repo.close()
