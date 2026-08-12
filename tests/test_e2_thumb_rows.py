"""E2 — queue/history rows expose thumbnail path; missing path is safe."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.queue_list import QueueList

_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00" + (b"\x08" * 64) + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01"
    b"\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xff\xd9"
)


def test_job_exposes_thumbnail_path(tmp_path: Path):
    repo = JobRepository(tmp_path / "t.db")
    job = repo.enqueue("https://example.com/x")
    assert job.thumbnail_path is None
    repo.merge_options(job.id, {"thumbnail_path": str(tmp_path / "a.jpg")})
    assert repo.get(job.id).thumbnail_path == str(tmp_path / "a.jpg")
    repo.close()


def test_queue_list_accepts_missing_and_present_thumb(tmp_path: Path):
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "q.db")
        missing = repo.enqueue("https://example.com/none", title="none")
        has = repo.enqueue("https://example.com/yes", title="yes")
        jpg = tmp_path / "t.jpg"
        jpg.write_bytes(_JPEG)
        repo.merge_options(has.id, {"thumbnail_path": str(jpg)})
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        assert missing.id in ql._rows
        assert has.id in ql._rows
        assert ql._rows[missing.id]["thumb_path"] is None
        assert ql._rows[has.id]["thumb_path"] == str(jpg)
        # Second update must reuse cache (path unchanged)
        ql.update_jobs(repo.list_jobs())
        assert ql._rows[has.id]["thumb_path"] == str(jpg)
        repo.close()
    finally:
        root.destroy()
