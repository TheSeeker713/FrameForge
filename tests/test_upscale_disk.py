"""Upscale chunked PNG disk/duration guards."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from frameforge.errors import DISK_SPACE, UPSCALE_LIMIT, UNKNOWN, classify_error
from frameforge.paths import ensure_output_tree, models_dir
from frameforge.upscale.disk import (
    PNG_BYTES_PER_PIXEL,
    UPSCALE_SCALE,
    DiskSpaceError,
    UpscaleDurationError,
    VideoMetrics,
    assert_upscale_guards,
    cleanup_job_frames,
    duration_warning_message,
    estimate_png_pipeline_bytes,
    frame_count,
    sweep_orphan_frame_dirs,
)
from frameforge.upscale.pipeline import UpscalePipeline


@pytest.fixture(scope="module", autouse=True)
def _ensure_x2_model():
    import subprocess

    ensure_output_tree()
    script = Path(__file__).resolve().parents[1] / "scripts" / "create_x2_onnx.py"
    subprocess.run(
        [str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "python.exe"), str(script)],
        check=False,
    )
    assert (models_dir() / "frameforge_x2_resize.onnx").exists() or list(models_dir().glob("*.onnx"))


def test_estimate_png_pipeline_bytes_formula():
    frames = frame_count(10.0, 30.0)
    assert frames == 300
    est = estimate_png_pipeline_bytes(width=1920, height=1080, frames=frames)
    src = 300 * 1920 * 1080 * PNG_BYTES_PER_PIXEL
    dst = 300 * (1920 * UPSCALE_SCALE) * (1080 * UPSCALE_SCALE) * PNG_BYTES_PER_PIXEL
    assert est == int(src + dst)
    capped = frame_count(3600.0, 30.0, max_frames=8)
    assert capped == 8


def test_refuse_when_free_less_than_estimate():
    metrics = VideoMetrics(width=1920, height=1080, fps=30.0, duration_sec=60.0)
    with pytest.raises(DiskSpaceError) as caught:
        assert_upscale_guards(
            metrics,
            max_frames=None,
            max_duration_minutes=15,
            free_bytes=1024,
            volume="C:\\",
        )
    err = caught.value
    assert err.category == DISK_SPACE
    assert classify_error(str(err)) == DISK_SPACE
    assert classify_error(str(err)) != UNKNOWN
    assert "need" in str(err).lower()
    assert "free" in str(err).lower()
    patch = err.option_patch()
    assert patch["disk_required_bytes"] > patch["disk_free_bytes"]
    assert patch["disk_estimated_bytes"] > 0


def test_duration_is_warning_not_hard_block():
    metrics = VideoMetrics(width=64, height=48, fps=10.0, duration_sec=3600.0)
    info = assert_upscale_guards(
        metrics,
        max_duration_minutes=15,
        free_bytes=10**18,
        volume="C:\\",
    )
    assert info["frames"] >= 1
    warn = duration_warning_message(metrics, warn_minutes=15)
    assert warn is not None
    assert "Long upscale" in warn
    legacy = UpscaleDurationError(duration_sec=3600.0, max_minutes=15)
    assert legacy.category == UPSCALE_LIMIT
    assert classify_error(str(legacy)) == UPSCALE_LIMIT
    assert classify_error(str(legacy)) != UNKNOWN


def test_cleanup_job_frames_tmpdir(tmp_path: Path):
    base = tmp_path / "job_9"
    (base / "frames").mkdir(parents=True)
    (base / "upscaled_frames").mkdir()
    (base / "frames" / "frame_000001.png").write_bytes(b"png")
    (base / "upscaled_frames" / "frame_000001.png").write_bytes(b"png")
    (base / "checkpoint.json").write_text("{}", encoding="utf-8")
    cleanup_job_frames(base, include_job_dir=False)
    assert not (base / "frames").exists()
    assert not (base / "upscaled_frames").exists()
    assert (base / "checkpoint.json").is_file()
    cleanup_job_frames(base, include_job_dir=True)
    assert not base.exists()


def test_sweep_orphan_skips_temp_dl(tmp_path: Path):
    temp = tmp_path / "temp"
    frames = temp / "job_1" / "frames"
    frames.mkdir(parents=True)
    (frames / "frame_000001.png").write_bytes(b"x")
    dl = temp / "dl"
    dl.mkdir()
    (dl / "clip.part").write_bytes(b"part")
    old = time.time() - 48 * 3600
    os.utime(frames, (old, old))
    removed = sweep_orphan_frame_dirs(temp, max_age_hours=24)
    assert removed >= 1
    assert not frames.exists()
    assert (dl / "clip.part").is_file()


def test_precheck_runs_when_max_frames_high(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tests.test_phase2_upscale import _make_sample_clip

    clip = _make_sample_clip(tmp_path / "in.mp4", seconds=0.5)
    monkeypatch.setattr(
        "frameforge.upscale.pipeline.video_metrics",
        lambda _p: VideoMetrics(width=1920, height=1080, fps=30.0, duration_sec=600.0),
    )
    monkeypatch.setattr("frameforge.upscale.pipeline.free_bytes_for", lambda _p: 2048)

    def _extract_must_not_run(*_a, **_k):
        raise AssertionError("extract_frames must not run after disk refuse")

    monkeypatch.setattr("frameforge.upscale.pipeline.extract_frame_range", _extract_must_not_run)
    pipe = UpscalePipeline(work_root=tmp_path / "work", max_frames=50_000, tile=64)
    with pytest.raises(DiskSpaceError):
        pipe.run(clip, job_key="huge")
    assert not (tmp_path / "work" / "huge" / "frames").exists()


@pytest.mark.timeout(180)
def test_successful_short_upscale_removes_frames_dir(tmp_path: Path):
    from tests.test_phase2_upscale import _make_sample_clip

    clip = _make_sample_clip(tmp_path / "clip.mp4", seconds=0.5)
    work = tmp_path / "work"
    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=work,
        max_frames=8,
        tile=64,
    )
    result = pipe.run(clip, job_key="jobClean", output_path=tmp_path / "out.mp4")
    assert result.output_path.exists()
    assert not (work / "jobClean" / "frames").exists()
    assert not (work / "jobClean" / "upscaled_frames").exists()
    assert not (work / "jobClean").exists()


def test_annotate_disk_space_persists_bytes_not_unknown(tmp_path: Path):
    from frameforge.db.repository import JobRepository
    from frameforge.error_report import format_full_error_report
    from frameforge.errors import annotate_job_error

    repo = JobRepository(tmp_path / "d.db")
    job = repo.enqueue("https://example.com/u")
    err = DiskSpaceError(
        estimated_bytes=10_000_000_000,
        required_bytes=13_000_000_000,
        free_bytes=1_000_000,
        volume="C:\\",
        margin=1.3,
        frames=1800,
        width=1920,
        height=1080,
    )
    annotate_job_error(repo, job.id, str(err), extra=err.option_patch())
    loaded = repo.get(job.id)
    assert loaded.options().get("error_category") == DISK_SPACE
    assert loaded.options().get("error_category") != UNKNOWN
    assert loaded.options().get("disk_free_bytes") == 1_000_000
    report = format_full_error_report(loaded)
    assert "disk_estimated_bytes" in report
    assert "disk_free_bytes" in report
    repo.close()
