"""A download and its upscale are one library card."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.library.ingest import publish_completed_downloads
from frameforge.library.scan import attach_scanned_file
from frameforge.library.store import LibraryStore
from frameforge.library.versions import mark_missing_files, remember_source


def _repo(tmp_path: Path) -> JobRepository:
    return JobRepository(tmp_path / "lib.db")


def test_publish_keeps_the_download_and_adds_the_upscale(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    store.mark_onboarded()
    download = tmp_path / "clip.mp4"
    download.write_bytes(b"d" * 32)
    upscale = tmp_path / "upscaled" / "clip_x4.upscaled.mp4"
    upscale.parent.mkdir()
    upscale.write_bytes(b"u" * 64)
    job = repo.enqueue("https://www.youtube.com/watch?v=abc", title="Clip")
    repo.update_status(job.id, "completed")
    repo.set_paths(job.id, download_path=str(download), output_path=str(upscale))
    assert publish_completed_downloads(repo, store) == 1
    assert publish_completed_downloads(repo, store) == 0
    item = store.get_by_job_id(job.id)
    assert item is not None
    assert item.source_url == "https://www.youtube.com/watch?v=abc"
    assert item.source_site == "youtube.com"
    files = store.list_files(item.id)
    roles = {row.role for row in files}
    assert roles == {"original", "upscaled"}
    assert Path(item.path).resolve() == upscale.resolve()
    assert download.is_file() and upscale.is_file()
    repo.close()


def test_source_url_rejects_non_http(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    src = tmp_path / "a.mp4"
    src.write_bytes(b"a" * 16)
    item = store.add_item(path=src, title="A")
    remember_source(store, item.id, "javascript:alert(1)")
    remember_source(store, item.id, "file:///C:/secret.mp4")
    remember_source(store, item.id, "")
    assert store.get(item.id).source_url is None
    repo.close()


def test_scanned_upscale_suffix_joins_the_same_card(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    src = tmp_path / "Interview.mp4"
    src.write_bytes(b"s" * 16)
    item = store.add_item(path=src, title="Interview", job_id=None)
    extra = tmp_path / "upscaled" / "Interview_x2.upscaled.mp4"
    extra.parent.mkdir()
    extra.write_bytes(b"e" * 16)
    assert attach_scanned_file(store, extra) is True
    files = store.list_files(item.id)
    assert any(row.role == "upscaled" and row.scale == 2 for row in files)
    assert attach_scanned_file(store, extra) is True
    assert len(store.list_files(item.id)) == 2
    repo.close()


def test_deleted_file_is_marked_missing(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    src = tmp_path / "gone.mp4"
    src.write_bytes(b"g" * 16)
    item = store.add_item(path=src, title="Gone")
    src.unlink()
    assert mark_missing_files(store) == 1
    file_row = store.list_files(item.id)[0]
    assert file_row.present is False
    assert src.exists() is False
    repo.close()


def test_probe_parses_rotation_and_leaves_duration_empty():
    from frameforge.library.probe import _parse

    parsed = _parse(
        {
            "format": {"size": "100"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "codec_name": "h264",
                    "pix_fmt": "yuv420p",
                    "avg_frame_rate": "30/1",
                    "side_data_list": [{"rotation": -90}],
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    assert parsed is not None
    assert parsed.duration is None
    assert parsed.width == 1080
    assert parsed.height == 1920
    assert parsed.rotation == 90
    assert parsed.acodec == "aac"
    assert parsed.fps == 30
