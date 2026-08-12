"""Tier 3.1 — probe and store source resolution on completed downloads."""

from __future__ import annotations

import subprocess
from pathlib import Path

from frameforge.db.migrate import current_version, migrate
from frameforge.db.connection import connect
from frameforge.db.repository import JobRepository


def _make_clip(path: Path, *, size: str = "640x360") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=5:duration=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return path


def test_migration_adds_resolution_columns(tmp_path: Path):
    db = tmp_path / "m.db"
    conn = connect(db)
    assert migrate(conn) >= 2
    assert current_version(conn) >= 2
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "source_width" in cols
    assert "source_height" in cols
    conn.close()


def test_probe_stores_resolution(tmp_path: Path):
    clip = _make_clip(tmp_path / "a.mp4", size="854x480")
    repo = JobRepository(tmp_path / "r.db")
    job = repo.enqueue("https://example.com/a")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(clip), output_path=str(clip))
    updated = repo.probe_and_store_resolution(job.id)
    assert updated.source_width == 854
    assert updated.source_height == 480
    loaded = repo.get(job.id)
    assert loaded.source_width == 854
    assert loaded.source_height == 480
    repo.close()


def test_probe_missing_file_sets_unknown(tmp_path: Path):
    repo = JobRepository(tmp_path / "u.db")
    job = repo.enqueue("https://example.com/missing")
    repo.update_status(job.id, "completed", progress=100)
    repo.set_paths(job.id, download_path=str(tmp_path / "nope.mp4"))
    updated = repo.probe_and_store_resolution(job.id)
    assert updated.source_width is None
    assert updated.source_height is None
    repo.close()


def test_probe_unreadable_does_not_crash(tmp_path: Path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    repo = JobRepository(tmp_path / "b.db")
    job = repo.enqueue("https://example.com/bad")
    repo.set_paths(job.id, download_path=str(bad))
    updated = repo.probe_and_store_resolution(job.id)
    assert updated.source_width is None
    assert updated.source_height is None
    repo.close()
