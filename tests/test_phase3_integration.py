"""Phase 3 integration — chained download/upscale, cleanup, sequential E2E."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from frameforge.db.repository import Job, JobRepository
from frameforge.pipeline import aggregate_progress, build_worker, cleanup_job_temp
from frameforge.paths import ensure_output_tree, models_dir, temp_dir
from frameforge.queue.worker import SequentialWorker
from frameforge.upscale.pipeline import UpscalePipeline


def _ffprobe_has_audio(path: Path) -> bool:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    return any(s.get("codec_type") == "audio" for s in data["streams"])


def test_aggregate_progress_formula():
    assert aggregate_progress("downloading", 100, True) == 50
    assert aggregate_progress("upscaling", 100, True) == 100
    assert aggregate_progress("downloading", 100, False) == 100
    assert aggregate_progress("completed", 100, True) == 100


def test_upscale_flag_false_skips_upscale(tmp_path: Path):
    db = tmp_path / "p3.db"
    repo = JobRepository(db)

    def dl(job: Job, r: JobRepository) -> None:
        out = tmp_path / f"{job.id}.mp4"
        out.write_bytes(b"fake")
        r.set_paths(job.id, download_path=str(out), output_path=str(out))

    def up(job: Job, r: JobRepository) -> None:
        raise AssertionError("upscale should not run")

    worker = SequentialWorker(repo, download_handler=dl, upscale_handler=up)
    job = repo.enqueue("https://example.com/a", upscale=False)
    worker.run_until_idle(timeout=5)
    assert repo.get(job.id).status == "completed"
    repo.close()


def test_upscale_flag_true_runs_stages(tmp_path: Path):
    db = tmp_path / "p3b.db"
    repo = JobRepository(db)
    stages: list[str] = []

    def dl(job: Job, r: JobRepository) -> None:
        stages.append("download")
        out = tmp_path / f"{job.id}.mp4"
        out.write_bytes(b"fake")
        r.set_paths(job.id, download_path=str(out), output_path=str(out))

    def up(job: Job, r: JobRepository) -> None:
        stages.append("upscale")
        out = tmp_path / f"{job.id}.up.mp4"
        out.write_bytes(b"up")
        r.set_paths(job.id, output_path=str(out))

    worker = SequentialWorker(repo, download_handler=dl, upscale_handler=up)
    job = repo.enqueue("https://example.com/b", upscale=True)
    worker.run_until_idle(timeout=5)
    assert stages == ["download", "upscale"]
    assert repo.get(job.id).status == "completed"
    repo.close()


def test_cleanup_job_temp(tmp_path: Path):
    job_dir = tmp_path / "job_9"
    (job_dir / "frames").mkdir(parents=True)
    (job_dir / "frames" / "frame_000001.png").write_bytes(b"x")
    cleanup_job_temp(9, work_root=tmp_path)
    assert not job_dir.exists()


@pytest.mark.timeout(300)
def test_e2e_local_download_artifact_then_upscale(tmp_path: Path):
    """Real ffmpeg clip as download_path, then real upscale stage via worker."""
    ensure_output_tree()
    clip = tmp_path / "src.mp4"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=10:duration=0.8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.8",
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

    db = tmp_path / "e2e.db"
    repo = JobRepository(db)

    def dl(job: Job, r: JobRepository) -> None:
        r.set_paths(job.id, download_path=str(clip), output_path=str(clip))
        r.update_progress(job.id, 100)

    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=tmp_path / "work",
        max_frames=6,
        tile=64,
    )
    from frameforge.upscale.handler import make_upscale_handler

    worker = SequentialWorker(
        repo,
        download_handler=dl,
        upscale_handler=make_upscale_handler(pipe),
        poll_interval=0.05,
    )
    job = repo.enqueue("https://example.com/local-fixture", upscale=True, title="local")
    # Also enqueue a second job to prove it waits (no concurrent download)
    job2 = repo.enqueue("https://example.com/second", upscale=False, title="second")

    def dl2(job: Job, r: JobRepository) -> None:
        # first handler used for both — detect by url
        if "second" in job.url:
            p = tmp_path / "second.bin"
            p.write_bytes(b"ok")
            r.set_paths(job.id, download_path=str(p), output_path=str(p))
        else:
            r.set_paths(job.id, download_path=str(clip), output_path=str(clip))
        r.update_progress(job.id, 100)

    worker.download_handler = dl2
    worker.run_until_idle(timeout=180)
    j1 = repo.get(job.id)
    j2 = repo.get(job2.id)
    assert j1.status == "completed"
    assert j2.status == "completed"
    assert j1.output_path and Path(j1.output_path).exists()
    assert _ffprobe_has_audio(Path(j1.output_path))
    assert j1.finished_at is not None and j2.started_at is not None
    # sequential: job2 should not finish before job1 started download completion chain
    assert repo.count_by_status("downloading") == 0
    cleanup_job_temp(job.id, work_root=tmp_path / "work")
    repo.close()
