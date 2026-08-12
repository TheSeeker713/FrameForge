"""Step 5 — Open folder / Reveal work with site-subfolder paths."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.paths import download_dir_for_site, frameforge_root
from frameforge.util.reveal import (
    containing_folder,
    explorer_select_command,
    open_job_folder,
    resolve_job_media_path,
    reveal_job_file,
)


def test_reveal_resolves_file_under_youtube_site_folder(tmp_path: Path):
    site_dir = tmp_path / "FrameForge" / "youtube"
    site_dir.mkdir(parents=True)
    media = site_dir / "clip.mp4"
    media.write_bytes(b"fake-mp4")
    repo = JobRepository(tmp_path / "r.db")
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="clip")
    repo.set_paths(job.id, download_path=str(media), output_path=str(media))
    loaded = repo.get(job.id)
    resolved = resolve_job_media_path(loaded)
    assert resolved == media.resolve()
    assert resolved.parent.name == "youtube"
    folder = containing_folder(resolved)
    assert folder == site_dir.resolve()
    assert open_job_folder(loaded, launch=False) == site_dir.resolve()
    assert reveal_job_file(loaded, launch=False) == site_dir.resolve()
    cmd = explorer_select_command(media)
    assert cmd[0] == "explorer"
    assert "youtube" in cmd[1]
    repo.close()


def test_download_dir_for_site_youtube_is_under_frameforge_root():
    dest = download_dir_for_site("youtube")
    assert dest.parent == frameforge_root()
    assert dest.name == "youtube"
