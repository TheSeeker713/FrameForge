"""Queue reset clears jobs and leaves media, cookies, and the home file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.queue.reset import QueueResetRefused, reset_queue


def _home(tmp_path: Path) -> tuple[JobRepository, Path, Path, Path]:
    home = tmp_path / "FrameForge"
    cookie = home / "cookies" / "example.txt"
    cookie.parent.mkdir(parents=True)
    cookie.write_text("netscape", encoding="utf-8")
    root_txt = home / "root.txt"
    root_txt.write_text("stay", encoding="utf-8-sig")
    media = home / "downloads" / "clip.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video-bytes")
    repo = JobRepository(home / "database" / "frameforge.db")
    return repo, media, cookie, root_txt


def test_reset_queue_clears_jobs_and_keeps_files(tmp_path: Path):
    repo, media, cookie, root_txt = _home(tmp_path)
    job = repo.enqueue("https://example.com/queued")
    repo.set_paths(job.id, download_path=str(media))
    repo.add_archive("https://example.com/archived", title="old", output_path=str(media))
    repo.set_setting("ui_scale", "1")
    repo.conn.execute(
        "INSERT INTO library_items(path, date_added, is_private) VALUES (?, ?, 0)",
        (str(media), "2026-01-01T00:00:00+00:00"),
    )
    repo.conn.commit()
    removed = reset_queue(repo)
    assert removed == 1
    assert repo.conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"] == 0
    assert repo.archive_lookup("https://example.com/archived") is None
    assert repo.get_setting("ui_scale") == "1"
    assert repo.conn.execute("SELECT COUNT(*) AS c FROM library_items").fetchone()["c"] == 1
    assert media.read_bytes() == b"video-bytes"
    assert cookie.read_text(encoding="utf-8") == "netscape"
    assert root_txt.read_text(encoding="utf-8-sig") == "stay"
    repo.close()


def test_reset_queue_refuses_while_downloading(tmp_path: Path):
    repo, media, _cookie, _root = _home(tmp_path)
    job = repo.enqueue("https://example.com/live")
    repo.update_status(job.id, "downloading")
    repo.set_paths(job.id, download_path=str(media))
    with pytest.raises(QueueResetRefused):
        reset_queue(repo)
    assert repo.get(job.id).status == "downloading"
    assert media.is_file()
    repo.close()


def test_cli_reset_queue_uses_frameforge_root(tmp_path: Path, monkeypatch):
    home = tmp_path / "FrameForge"
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(home))
    media = home / "clip.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"keep")
    profile = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads" / "FrameForge"
    profile_existed = profile.exists()
    repo = JobRepository(home / "database" / "frameforge.db")
    repo.enqueue("https://example.com/cli")
    repo.close()
    from frameforge.__main__ import main

    assert main(["--reset-queue"]) == 0
    check = JobRepository(home / "database" / "frameforge.db")
    assert check.conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"] == 0
    check.close()
    assert media.read_bytes() == b"keep"
    if not profile_existed:
        assert not profile.exists()
