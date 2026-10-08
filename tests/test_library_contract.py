"""Albums are database links. Indexing and unlinking do not move or delete the file."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.library.ingest import publish_completed_downloads
from frameforge.library.store import LibraryStore


def _clip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media")
    return path


def test_album_and_unlink_leave_the_file(tmp_path: Path):
    repo = JobRepository(tmp_path / "c.db")
    store = LibraryStore(repo)
    src = _clip(tmp_path / "downloads" / "site" / "clip.mp4")
    store.complete_onboarding(tmp_path / "Lib")
    item = store.add_item(path=src, title="Clip")
    album = store.create_album("Evening")
    placed = store.place_in_album(item.id, album.id)
    assert Path(placed.path).resolve() == src.resolve()
    assert src.is_file()
    assert src.read_bytes() == b"media"
    store.remove_item(placed.id)
    assert src.is_file()
    assert store.list_items() == []
    repo.close()


def test_indexing_a_completed_download_does_not_relocate_it(tmp_path: Path, monkeypatch):
    root = tmp_path / "FrameForge"
    root.mkdir()
    monkeypatch.setattr("frameforge.paths.frameforge_root", lambda: root)
    repo = JobRepository(tmp_path / "q.db")
    store = LibraryStore(repo)
    src = _clip(root / "downloads" / "youtube" / "talk.mp4")
    job = repo.enqueue("https://example.com/talk", title="Talk")
    repo.update_status(job.id, "completed")
    repo.set_paths(job.id, download_path=str(src), output_path=str(src))
    added = publish_completed_downloads(repo, store)
    assert added == 1
    assert src.is_file()
    assert Path(store.list_items()[0].path).resolve() == src.resolve()
    assert not (root / "Library" / "Uncategorized" / "talk.mp4").exists()
    repo.close()
