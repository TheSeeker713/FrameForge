"""Final Phase 5 verification suite — real checks across the stack."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import parse_file
from frameforge.env_check import check_environment
from frameforge.paths import ensure_output_tree, models_dir
from frameforge.queue.worker import SequentialWorker
from frameforge.upscale.pipeline import UpscalePipeline


FIX = Path(__file__).parent / "fixtures"


def test_env_ok():
    ensure_output_tree()
    report = check_environment()
    assert report["ok"] is True
    assert report["onnx"]["has_dml"] or report["onnx"]["has_cpu"]
    assert report["impersonation"]["ok"] is True
    assert report["impersonation"]["chrome_available"] is True


def test_sequential_invariant_sqlite(tmp_path: Path):
    repo = JobRepository(tmp_path / "final.db")
    repo.enqueue("https://example.com/1")
    repo.enqueue("https://example.com/2")
    a = repo.claim_next_pending()
    b = repo.claim_next_pending()
    assert a is not None
    assert b is None
    assert repo.count_by_status("downloading") == 1
    repo.close()


def test_bulk_fixtures_parse():
    items = parse_file(FIX / "bulk_urls.txt")
    assert len(items) >= 3


@pytest.mark.timeout(180)
def test_final_upscale_audio_paths(tmp_path: Path):
    ensure_output_tree()
    clip = tmp_path / "final.mp4"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=48x32:rate=8:duration=0.6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=600:duration=0.6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(clip),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    model = models_dir() / "frameforge_x2_resize.onnx"
    pipe = UpscalePipeline(model_path=model, work_root=tmp_path / "w", max_frames=4, tile=64)
    result = pipe.run(clip, job_key="final", output_path=tmp_path / "out.mp4")
    assert result.output_path.exists()
    assert result.output_size[0] > result.input_size[0]
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(result.output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(probe.stdout)
    assert any(s.get("codec_type") == "audio" for s in data["streams"])


def test_worker_non_overlap_stub(tmp_path: Path):
    import time

    from frameforge.db.repository import Job

    repo = JobRepository(tmp_path / "seq.db")
    windows = []

    def h(job: Job, r: JobRepository) -> None:
        s = time.time()
        time.sleep(0.08)
        e = time.time()
        windows.append((s, e))
        r.set_paths(job.id, download_path=str(tmp_path / f"{job.id}.bin"))

    w = SequentialWorker(repo, download_handler=h)
    repo.enqueue("https://example.com/a")
    repo.enqueue("https://example.com/b")
    w.run_until_idle(timeout=10)
    windows.sort()
    assert windows[0][1] <= windows[1][0] + 1e-3
    repo.close()
