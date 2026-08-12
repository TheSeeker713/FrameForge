"""Tier 4.3 — open folder / reveal file helpers and GUI wiring."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.app import FrameForgeApp
from frameforge.util.reveal import (
    RevealError,
    containing_folder,
    explorer_select_command,
    open_job_folder,
    resolve_job_media_path,
    reveal_job_file,
)


def test_resolve_directory_for_sample_file(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake")
    repo = JobRepository(tmp_path / "r.db")
    job = repo.enqueue("https://example.com/x", title="x")
    repo.set_paths(job.id, download_path=str(media), output_path=str(media))
    job = repo.get(job.id)
    resolved = resolve_job_media_path(job)
    assert resolved == media.resolve()
    folder = containing_folder(resolved)
    assert folder == tmp_path.resolve()
    # dry-run launch=False — no Explorer popup in tests
    assert open_job_folder(job, launch=False) == tmp_path.resolve()
    assert reveal_job_file(job, launch=False) == tmp_path.resolve()
    cmd = explorer_select_command(media)
    assert cmd[0] == "explorer"
    assert str(media.resolve()) in cmd[1]
    repo.close()


def test_missing_path_raises_clear_error(tmp_path: Path):
    repo = JobRepository(tmp_path / "m.db")
    job = repo.enqueue("https://example.com/missing")
    with pytest.raises(RevealError, match="No local file"):
        resolve_job_media_path(job)
    repo.set_paths(job.id, download_path=str(tmp_path / "gone.mp4"))
    job = repo.get(job.id)
    with pytest.raises(RevealError, match="No local file"):
        open_job_folder(job, launch=False)
    repo.close()


def test_gui_exposes_open_and_reveal_actions(tmp_path: Path):
    try:
        repo = JobRepository(tmp_path / "g.db")
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        assert hasattr(app, "open_folder_btn")
        assert hasattr(app, "reveal_file_btn")
        assert callable(app.open_folder_selected)
        assert callable(app.reveal_file_selected)
        media = tmp_path / "out.mp4"
        media.write_bytes(b"x")
        job = repo.enqueue("https://example.com/ok")
        repo.update_status(job.id, "completed", progress=100)
        repo.set_paths(job.id, download_path=str(media), output_path=str(media))
        app.queue_list.set_selected({job.id})
        app._selected_ids = {job.id}
        # Prefer output over download when both set
        folder = open_job_folder(repo.get(job.id), launch=False)
        assert folder == tmp_path.resolve()
    finally:
        app.destroy()
        repo.close()
