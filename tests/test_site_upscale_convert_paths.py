"""Step 4 — upscale and convert outputs use per-site directories."""

from __future__ import annotations

from pathlib import Path

from frameforge.convert.handler import convert_output_path_for_job
from frameforge.db.repository import JobRepository
from frameforge.paths import converted_dir_for_site, upscaled_dir_for_site
from frameforge.upscale.handler import upscale_output_path_for_job


def test_upscale_path_includes_youtube_segment(tmp_path: Path):
    repo = JobRepository(tmp_path / "u.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc")
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    out = upscale_output_path_for_job(repo.get(job.id), src)
    assert out.parent == upscaled_dir_for_site("youtube")
    assert "youtube" in out.parts
    assert "upscaled" in out.parts
    assert out.parent.is_dir()
    repo.close()


def test_convert_path_includes_x_com_segment(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    job = repo.enqueue("https://x.com/user/status/1")
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    out = convert_output_path_for_job(repo.get(job.id), src)
    assert out.parent == converted_dir_for_site("x.com")
    assert "x.com" in out.parts
    assert "converted" in out.parts
    assert out.name.endswith(".mp3")
    assert out.parent.is_dir()
    repo.close()
