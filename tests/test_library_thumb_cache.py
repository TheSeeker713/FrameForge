"""Thumbnail keys, seek choice, black-frame retry, misses, and cache pruning."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.thumbnails import thumbnail_url_from_info
from frameforge.library.store import LibraryStore
from frameforge.library.thumbs import (
    _default_run,
    cache_key,
    extract_library_thumb,
    ffmpeg_still_argv,
    prune_thumb_cache,
    save_thumb_row,
    seek_time,
    thumb_is_current,
)


def test_cache_key_changes_when_size_or_mtime_changes(tmp_path: Path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"v" * 20)
    first = cache_key(src, 20, 100)
    assert cache_key(src, 21, 100) != first
    assert cache_key(src, 20, 101) != first
    assert cache_key(src, 20, 100) == first


def test_seek_time_for_unknown_short_and_long_clips():
    assert seek_time(None) == 1.0
    assert seek_time(0.5) == 0.0
    assert seek_time(10) == 1.0
    assert seek_time(120) == 5.0


def test_black_frame_retries_and_keeps_the_brighter_still(tmp_path: Path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"v" * 64)
    dest = tmp_path / "out.jpg"
    scores = iter([10.0, 40.0])
    seeks: list[str] = []

    def run(argv: list[str]) -> int:
        seeks.append(argv[argv.index("-ss") + 1])
        out = Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\xff\xd8" + b"j" * 40)
        return 0

    still = extract_library_thumb(
        src,
        dest,
        duration=10,
        ffmpeg="ffmpeg",
        run=run,
        luma=lambda _path: next(scores),
    )
    assert still == dest
    assert dest.is_file()
    assert seeks[0] == "1.000"
    assert seeks[1] == "2.500"
    assert "CREATE_NO_WINDOW" not in " ".join(ffmpeg_still_argv("ffmpeg", src, dest, 1))
    assert "-ss" in ffmpeg_still_argv("ffmpeg", src, dest, 1)


def test_miss_is_kept_until_the_key_changes(tmp_path: Path):
    repo = JobRepository(tmp_path / "t.db")
    store = LibraryStore(repo)
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"v" * 32)
    item = store.add_item(path=src, title="Clip")
    file_id = store.list_files(item.id)[0].id
    save_thumb_row(store, file_id, cache_key_value="abc", status="miss", error="bad file")
    assert thumb_is_current(store, file_id, "abc") is True
    assert thumb_is_current(store, file_id, "other") is False
    row = store.get_thumb(file_id)
    assert row is not None and row.attempts == 1 and row.status == "miss"
    repo.close()


def test_prune_drops_the_oldest_thumbs_past_the_cap(tmp_path: Path, monkeypatch):
    repo = JobRepository(tmp_path / "t.db")
    store = LibraryStore(repo)
    root = tmp_path / "thumbs" / "library" / "aa"
    root.mkdir(parents=True)
    monkeypatch.setattr("frameforge.paths.thumbnails_dir", lambda: tmp_path / "thumbs")
    old = root / "old.jpg"
    new = root / "new.jpg"
    old.write_bytes(b"a" * 100)
    new.write_bytes(b"b" * 100)
    first = store.add_item(path=tmp_path / "a.mp4", title="A")
    second = store.add_item(path=tmp_path / "b.mp4", title="B")
    old_id = store.list_files(first.id)[0].id
    new_id = store.list_files(second.id)[0].id
    save_thumb_row(store, old_id, cache_key_value="old", status="ok", thumb_path=str(old))
    save_thumb_row(store, new_id, cache_key_value="new", status="ok", thumb_path=str(new))
    store.conn.execute(
        "UPDATE library_thumbs SET last_used = ? WHERE file_id = ?",
        ("2000-01-01T00:00:00+00:00", old_id),
    )
    store.conn.execute(
        "UPDATE library_thumbs SET last_used = ? WHERE file_id = ?",
        ("2026-01-01T00:00:00+00:00", new_id),
    )
    store.conn.commit()
    removed = prune_thumb_cache(store, max_bytes=100)
    assert removed >= 1
    assert not old.is_file()
    assert new.is_file()
    repo.close()


def test_extract_passes_create_no_window_on_windows(monkeypatch):
    seen: dict[str, int] = {}

    def fake_run(_argv, **kwargs):
        seen["flags"] = kwargs.get("creationflags", 0)

        class Proc:
            returncode = 0

        return Proc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    _default_run(["ffmpeg", "-version"])
    if sys.platform == "win32":
        assert seen["flags"] == subprocess.CREATE_NO_WINDOW
    else:
        assert seen["flags"] == 0


def test_remote_thumbnail_url_rejects_file_scheme():
    assert thumbnail_url_from_info({"thumbnail": "file:///C:/secret.jpg"}) is None
    assert thumbnail_url_from_info({"thumbnail": "https://example.com/a.jpg"}) == "https://example.com/a.jpg"
