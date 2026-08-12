"""C3 — bounded LRU thumbnail cache; hits must not reopen the file."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from frameforge.gui.thumb_cache import LruCache

_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00" + (b"\x08" * 64) + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01"
    b"\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xff\xd9"
)


def test_lru_evicts_least_recently_used():
    cache: LruCache[int] = LruCache(maxsize=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert "b" not in cache
    assert "a" in cache
    assert "c" in cache
    assert len(cache) == 2


def test_lru_hit_does_not_count_as_miss():
    cache: LruCache[str] = LruCache(maxsize=4)
    cache.put("x", "img")
    assert cache.misses == 0
    assert cache.get("x") == "img"
    assert cache.hits == 1
    assert cache.get("missing") is None
    assert cache.misses == 1


def test_queue_list_cache_hit_does_not_reopen(tmp_path: Path):
    import pytest

    try:
        import customtkinter as ctk

        from frameforge.db.repository import JobRepository
        from frameforge.gui.queue_list import QueueList
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    root = ctk.CTk()
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "t.db")
        jpg = tmp_path / "a.jpg"
        jpg.write_bytes(_JPEG)
        job = repo.enqueue("https://example.com/a", title="A")
        repo.merge_options(job.id, {"thumbnail_path": str(jpg)})
        ql = QueueList(root)
        opens: list[str] = []
        real_open = Image.open

        def spy_open(path):
            opens.append(str(path))
            return real_open(path)

        ql._open_image = spy_open
        ql.update_jobs(repo.list_jobs())
        assert opens == [str(jpg)]
        ql.update_jobs(repo.list_jobs())
        assert opens == [str(jpg)]
        # Force a cache lookup without row short-circuit
        ql._rows[job.id]["thumb_path"] = None
        ql._apply_thumb(ql._rows[job.id], repo.get(job.id))
        assert opens == [str(jpg)]
        assert ql._thumb_cache.hits >= 1
        repo.close()
    finally:
        root.destroy()
