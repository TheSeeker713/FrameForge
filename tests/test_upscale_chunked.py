"""Chunked upscale: one PNG chunk at a time, not a full-film dump."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frameforge.paths import ensure_output_tree, models_dir
from frameforge.upscale.disk import (
    DEFAULT_CHUNK_FRAMES,
    PNG_BYTES_PER_PIXEL,
    UPSCALE_SCALE,
    VideoMetrics,
    assert_upscale_guards,
    estimate_chunk_pipeline_bytes,
    estimate_png_pipeline_bytes,
    frame_count,
)
from frameforge.upscale.ffmpeg_utils import extract_frame_range, has_audio, video_size
from frameforge.upscale.pipeline import UpscalePipeline
from frameforge.util.process_tree import DownloadCancelled
from tests.test_phase2_upscale import _ffprobe, _make_sample_clip


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


def test_chunk_disk_estimate_is_not_full_film():
    hour = VideoMetrics(width=1920, height=1080, fps=30.0, duration_sec=3600.0)
    full_frames = frame_count(hour.duration_sec, hour.fps)
    assert full_frames == 108_000
    full = estimate_png_pipeline_bytes(width=1920, height=1080, frames=full_frames)
    chunk = estimate_chunk_pipeline_bytes(
        width=1920, height=1080, chunk_frames=DEFAULT_CHUNK_FRAMES
    )
    expected_chunk = DEFAULT_CHUNK_FRAMES * 1920 * 1080 * PNG_BYTES_PER_PIXEL * (
        1 + UPSCALE_SCALE * UPSCALE_SCALE
    )
    assert chunk == int(expected_chunk)
    assert chunk < full / 100
    info = assert_upscale_guards(
        hour,
        max_duration_minutes=15,
        chunk_frames=DEFAULT_CHUNK_FRAMES,
        free_bytes=10**18,
        volume="C:\\",
    )
    assert info["chunk_frames"] == DEFAULT_CHUNK_FRAMES
    assert info["estimated_bytes"] == chunk


def test_extract_frame_range_subset(tmp_path: Path):
    clip = _make_sample_clip(tmp_path / "in.mp4", seconds=1.0)
    frames = extract_frame_range(clip, tmp_path / "frames", start_frame=0, count=3, fps=10.0)
    assert 1 <= len(frames) <= 3
    assert all(p.exists() for p in frames)


@pytest.mark.timeout(180)
def test_chunked_short_clip_2x_and_cleans_png(tmp_path: Path):
    clip = _make_sample_clip(tmp_path / "clip.mp4", seconds=1.0)
    assert has_audio(clip)
    in_w, in_h = video_size(clip)
    work = tmp_path / "work"
    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=work,
        max_frames=6,
        tile=64,
        chunk_frames=2,
    )
    result = pipe.run(clip, job_key="chunked", output_path=tmp_path / "out.mp4")
    assert result.output_path.exists()
    out_w, out_h = result.output_size
    assert out_w > in_w and out_h > in_h
    probe = _ffprobe(result.output_path)
    assert any(s.get("codec_type") == "audio" for s in probe["streams"])
    assert not (work / "chunked" / "frames").exists()
    assert not (work / "chunked").exists()


@pytest.mark.timeout(180)
def test_cancel_between_chunks_then_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clip = _make_sample_clip(tmp_path / "clip.mp4", seconds=1.0)
    work = tmp_path / "work"
    assembled = {"n": 0}
    from frameforge.upscale import pipeline as pipe_mod

    real_assemble = pipe_mod.assemble_video

    def _count_assemble(*args, **kwargs):
        assembled["n"] += 1
        return real_assemble(*args, **kwargs)

    monkeypatch.setattr(pipe_mod, "assemble_video", _count_assemble)
    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=work,
        max_frames=6,
        tile=64,
        chunk_frames=2,
    )

    def should_stop() -> bool:
        return assembled["n"] >= 1

    with pytest.raises(DownloadCancelled):
        pipe.run(clip, job_key="jobC", output_path=tmp_path / "partial.mp4", should_stop=should_stop)

    ckpt = json.loads((work / "jobC" / "checkpoint.json").read_text(encoding="utf-8"))
    assert ckpt["completed_chunks"] >= 1
    assert (work / "jobC" / "segments" / "chunk_0000.mp4").exists()

    result = pipe.run(clip, job_key="jobC", output_path=tmp_path / "out.mp4")
    assert result.output_path.exists()
    assert any(s.get("codec_type") == "audio" for s in _ffprobe(result.output_path)["streams"])
