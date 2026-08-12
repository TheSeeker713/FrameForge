"""Step 3.1 — real ffmpeg convert-to-MP3 pipeline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from frameforge.convert.mp3 import convert_to_mp3
from frameforge.paths import converted_dir, ensure_output_tree


def _make_clip(path: Path, *, seconds: float = 0.6) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=64x48:rate=8:duration={seconds}",
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


def test_convert_local_clip_writes_mp3(tmp_path: Path):
    clip = _make_clip(tmp_path / "src.mp4")
    out = tmp_path / "out.mp3"
    percents: list[float] = []
    result = convert_to_mp3(clip, out, progress_cb=percents.append)
    assert result == out
    assert out.is_file()
    assert out.stat().st_size > 0
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    info = json.loads(probe.stdout)
    codecs = [s.get("codec_name") for s in info.get("streams") or []]
    assert "mp3" in codecs
    assert percents[0] == 0.0
    assert percents[-1] == 100.0


def test_convert_missing_input_errors(tmp_path: Path):
    missing = tmp_path / "nope.mp4"
    with pytest.raises(FileNotFoundError, match="ffmpeg"):
        convert_to_mp3(missing, tmp_path / "x.mp3")


def test_converted_dir_exists_after_ensure():
    ensure_output_tree()
    assert converted_dir().is_dir()
