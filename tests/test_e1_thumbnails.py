"""E1 — thumbnail cache on probe/download; missing thumbs are non-fatal."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.thumbnails import (
    cache_job_thumbnail,
    thumbnail_path_for_job,
    thumbnail_url_from_info,
)
from frameforge.paths import ensure_output_tree, thumbnails_dir

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


def test_thumbnail_url_from_info():
    assert thumbnail_url_from_info({}) is None
    assert thumbnail_url_from_info({"thumbnail": "https://cdn.example/a.jpg"}) == (
        "https://cdn.example/a.jpg"
    )
    assert (
        thumbnail_url_from_info(
            {"thumbnails": [{"url": "https://cdn.example/small.jpg"}, {"url": "https://cdn.example/big.jpg"}]}
        )
        == "https://cdn.example/big.jpg"
    )


def test_cache_thumbnail_from_file_and_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    src = tmp_path / "src.jpg"
    src.write_bytes(_JPEG)
    repo = JobRepository(tmp_path / "t.db")
    job = repo.enqueue("https://example.com/with-thumb")
    path = cache_job_thumbnail(repo, job.id, thumbnail_url=src.as_uri())
    assert path is not None
    assert path.is_file()
    assert path.parent == thumbnails_dir()
    assert repo.get(job.id).thumbnail_path == str(path)
    assert Path(repo.get(job.id).options()["thumbnail_path"]).exists()

    bare = repo.enqueue("https://example.com/no-thumb")
    assert cache_job_thumbnail(repo, bare.id, info={}) is None
    assert repo.get(bare.id).thumbnail_path is None
    assert cache_job_thumbnail(repo, bare.id, thumbnail_url="https://127.0.0.1:1/missing.jpg") is None
    assert repo.get(bare.id).status == "pending"
    expected = thumbnail_path_for_job(job.id)
    assert expected.name.startswith(str(job.id))
    repo.close()
