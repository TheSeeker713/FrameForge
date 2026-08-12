"""E3 — thumbnail browser listing and selection callback."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.download.thumbnails import list_thumbnail_jobs
from frameforge.gui.app import FrameForgeApp

_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00" + (b"\x08" * 64) + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01"
    b"\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xff\xd9"
)


def test_list_thumbnail_jobs_skips_missing(tmp_path: Path):
    repo = JobRepository(tmp_path / "t.db")
    jpg = tmp_path / "a.jpg"
    jpg.write_bytes(_JPEG)
    with_thumb = repo.enqueue("https://example.com/a", title="A")
    without = repo.enqueue("https://example.com/b", title="B")
    gone = repo.enqueue("https://example.com/c", title="C")
    repo.merge_options(with_thumb.id, {"thumbnail_path": str(jpg)})
    repo.merge_options(gone.id, {"thumbnail_path": str(tmp_path / "missing.jpg")})
    listed = list_thumbnail_jobs(repo)
    ids = [j.id for j in listed]
    assert with_thumb.id in ids
    assert without.id not in ids
    assert gone.id not in ids
    repo.close()


def test_focus_job_selects_queue_and_history(tmp_path: Path):
    try:
        repo = JobRepository(tmp_path / "g.db")
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        jpg = tmp_path / "a.jpg"
        jpg.write_bytes(_JPEG)
        job = repo.enqueue("https://example.com/a", title="A")
        repo.update_status(job.id, "completed", progress=100)
        repo.merge_options(job.id, {"thumbnail_path": str(jpg)})
        app.refresh_queue()
        assert app.focus_job(job.id) is True
        assert job.id in app.queue_list.selected_ids
        assert job.id in app.history_list.selected_ids
        assert app.focus_job(99999) is False
        thumbs = list_thumbnail_jobs(repo)
        assert thumbs and thumbs[0].id == job.id
    finally:
        app.destroy()
        repo.close()
