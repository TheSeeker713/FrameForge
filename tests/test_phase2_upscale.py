"""Phase 2 upscale tests — real local clip, tiling, stop/resume, audio preserve."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from frameforge.paths import ensure_output_tree, models_dir
from frameforge.upscale.ffmpeg_utils import extract_frames, has_audio, video_size
from frameforge.upscale.onnx_upscaler import OnnxUpscaler
from frameforge.upscale.pipeline import UpscalePipeline


def _make_sample_clip(path: Path, seconds: float = 1.0, size: str = "64x48") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}:rate=10:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=880:duration={seconds}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert path.exists()
    return path


def _ffprobe(path: Path) -> dict:
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
    return json.loads(proc.stdout)


@pytest.fixture(scope="module", autouse=True)
def _ensure_x2_model():
    ensure_output_tree()
    script = Path(__file__).resolve().parents[1] / "scripts" / "create_x2_onnx.py"
    subprocess.run(
        [str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "python.exe"), str(script)],
        check=False,
    )
    # Prefer x2 model for tests
    assert (models_dir() / "frameforge_x2_resize.onnx").exists() or list(models_dir().glob("*.onnx"))


def test_extract_frames_real(tmp_path: Path):
    clip = _make_sample_clip(tmp_path / "in.mp4", seconds=0.5)
    frames = extract_frames(clip, tmp_path / "frames")
    assert len(frames) >= 3
    assert all(p.exists() for p in frames)


def test_onnx_upscale_increases_resolution(tmp_path: Path):
    import cv2
    import numpy as np

    img = np.zeros((32, 48, 3), dtype=np.uint8)
    img[:] = (20, 80, 160)
    src = tmp_path / "f.png"
    cv2.imwrite(str(src), img)
    upscaler = OnnxUpscaler(model_path=models_dir() / "frameforge_x2_resize.onnx", tile=64)
    out = upscaler.upscale_image(cv2.imread(str(src)))
    assert out.shape[0] >= 64
    assert out.shape[1] >= 96


@pytest.mark.timeout(180)
def test_pipeline_stop_resume_and_audio(tmp_path: Path):
    clip = _make_sample_clip(tmp_path / "clip.mp4", seconds=1.0)
    assert has_audio(clip)
    in_w, in_h = video_size(clip)
    work = tmp_path / "work"
    pipe = UpscalePipeline(
        model_path=models_dir() / "frameforge_x2_resize.onnx",
        work_root=work,
        max_frames=8,
        tile=64,
    )
    stop_at = {"n": 0}

    def should_stop() -> bool:
        stop_at["n"] += 1
        return stop_at["n"] >= 3

    with pytest.raises(RuntimeError, match="stopped"):
        pipe.run(clip, job_key="jobA", output_path=tmp_path / "partial.mp4", should_stop=should_stop)

    ckpt = json.loads((work / "jobA" / "checkpoint.json").read_text(encoding="utf-8"))
    assert ckpt["completed_frames"] >= 1

    result = pipe.run(clip, job_key="jobA", output_path=tmp_path / "out.mp4")
    assert result.output_path.exists()
    out_w, out_h = result.output_size
    assert out_w > in_w and out_h > in_h
    probe = _ffprobe(result.output_path)
    assert any(s.get("codec_type") == "audio" for s in probe["streams"])
    assert any(s.get("codec_type") == "video" for s in probe["streams"])
