"""Completed-job thumbnails: sidecar cache, backfill, card image or placeholder."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.thumbnails import (
    backfill_missing_thumbnails,
    cache_job_thumbnail,
    sidecar_thumbnail_near,
    thumbnail_path_for_job,
)
from frameforge.download.ytdlp import DownloadResult, YtDlpDownloader
from frameforge.paths import ensure_output_tree
from frameforge.ui_flet.components.job_card import build_job_card
from frameforge.ui_flet.job_view import card_view

# 1x1 JPEG
_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00"
    b"\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01"
    b"\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07"
    b"\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x3f\xff\xd9"
)


def test_cli_writes_thumbnail_flag():
    dl = YtDlpDownloader(output_dir=Path("."), use_aria2c=False)
    cmd = dl._build_cli_cmd("https://example.com/v")
    assert "--write-thumbnail" in cmd
    assert dl.build_opts()["writethumbnail"] is True


def test_sidecar_near_media_and_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    media = tmp_path / "clip [abc].mp4"
    media.write_bytes(b"not-a-real-video")
    side = tmp_path / "clip [abc].jpg"
    side.write_bytes(_JPEG)
    assert sidecar_thumbnail_near(media) == side
    repo = JobRepository(tmp_path / "t.db")
    job = repo.enqueue("https://example.com/clip")
    path = cache_job_thumbnail(repo, job.id, media_path=media, extract_still=False)
    assert path is not None
    assert path.is_file()
    assert path.parent.name == "thumbnails" or path == thumbnail_path_for_job(job.id, ".jpg")
    assert repo.get(job.id).thumbnail_path == str(path)
    repo.close()


def test_backfill_completed_missing_thumb(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    media = tmp_path / "done.mp4"
    media.write_bytes(b"not-a-real-video")
    (tmp_path / "done.webp").write_bytes(_JPEG)
    repo = JobRepository(tmp_path / "b.db")
    job = repo.enqueue("https://example.com/done", title="done")
    repo.set_paths(job.id, download_path=str(media), output_path=str(media))
    repo.update_status(job.id, "completed", progress=100)
    assert repo.get(job.id).thumbnail_path is None
    n = backfill_missing_thumbnails(repo, extract_still=False)
    assert n == 1
    loaded = repo.get(job.id)
    assert loaded.thumbnail_path
    assert Path(loaded.thumbnail_path).is_file()
    repo.close()


def test_handler_stores_thumb_from_sidecar(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    out = tmp_path / "dl"
    out.mkdir()
    repo = JobRepository(tmp_path / "h.db")
    dl = YtDlpDownloader(output_dir=out, archive_file=tmp_path / "a.txt", use_aria2c=False)

    def fake_download(url: str, **kwargs: object):
        path = out / "x.mp4"
        path.write_bytes(b"not-a-real-video")
        (out / "x.jpg").write_bytes(_JPEG)
        return DownloadResult(path=path, title="x", info={"thumbnail": None})

    dl.download = fake_download  # type: ignore[method-assign]
    handler = make_download_handler(dl)
    job = repo.enqueue("https://example.com/watch?v=abc")
    repo.update_status(job.id, "downloading")
    handler(job, repo)
    stored = repo.get(job.id).thumbnail_path
    assert stored
    assert Path(stored).is_file()
    repo.close()


def test_card_shows_image_or_explicit_placeholder(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    repo = JobRepository(tmp_path / "c.db")
    bare = repo.enqueue("https://example.com/bare", title="bare")
    repo.update_status(bare.id, "completed", progress=100)
    card = build_job_card(bare, selected=False, expanded=False, show_progress=False)
    view = card_view(bare)
    assert view["thumbnail_path"] is None
    kinds = []

    def _walk(ctrl):
        data = getattr(ctrl, "data", None)
        if isinstance(data, dict) and data.get("kind") in {"thumb_image", "thumb_placeholder"}:
            kinds.append(data["kind"])
        content = getattr(ctrl, "content", None)
        if content is not None:
            _walk(content)
        controls = getattr(ctrl, "controls", None)
        if controls:
            for child in controls:
                _walk(child)

    _walk(card)
    assert "thumb_placeholder" in kinds

    jpg = tmp_path / "card.jpg"
    jpg.write_bytes(_JPEG)
    has = repo.enqueue("https://example.com/has", title="has")
    repo.update_status(has.id, "completed", progress=100)
    repo.merge_options(has.id, {"thumbnail_path": str(jpg)})
    loaded = repo.get(has.id)
    card2 = build_job_card(loaded, selected=False, expanded=False, show_progress=False)
    kinds2: list[str] = []

    def _walk2(ctrl):
        data = getattr(ctrl, "data", None)
        if isinstance(data, dict) and data.get("kind") in {"thumb_image", "thumb_placeholder"}:
            kinds2.append(data["kind"])
            assert data.get("src") == str(jpg)
        content = getattr(ctrl, "content", None)
        if content is not None:
            _walk2(content)
        controls = getattr(ctrl, "controls", None)
        if controls:
            for child in controls:
                _walk2(child)

    _walk2(card2)
    assert "thumb_image" in kinds2
    repo.close()
