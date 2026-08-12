"""Bulk import: YouTube watch/shorts/youtu.be, markdown links, encoding, no auto-start."""

from __future__ import annotations

import time
from pathlib import Path

from frameforge.db.repository import Job, JobRepository
from frameforge.download.bulk_import import confirm_add, parse_file, parse_lines, preview_import
from frameforge.queue.worker import SequentialWorker

FIX = Path(__file__).parent / "fixtures"

WATCH = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
SHORTS = "https://www.youtube.com/shorts/abcdefghijk"
YOUTU = "https://youtu.be/jNQXAC9IVRw"


def test_parse_bare_youtube_watch_shorts_youtu_be():
    items = parse_file(FIX / "youtube_bulk.md")
    urls = [i.url for i in items]
    assert WATCH in urls
    assert f"{WATCH}&t=12s" in urls
    assert SHORTS in urls
    assert YOUTU in urls
    assert f"{YOUTU}?si=ShareParam" in urls
    assert "https://x.com/example/status/1234567890" in urls
    # trailing period stripped; same watch URL not duplicated
    assert urls.count(WATCH) == 1
    assert len(items) == 6


def test_parse_markdown_links_and_inline_urls():
    items = parse_file(FIX / "youtube_md_links.md")
    urls = [i.url for i in items]
    assert WATCH in urls
    assert SHORTS in urls
    assert YOUTU in urls
    assert "https://youtu.be/dQw4w9WgXcQ" in urls
    zoo = next(i for i in items if i.url == WATCH)
    assert zoo.title == "Me at the zoo"
    assert len(items) == 4


def test_empty_file_zero_urls(tmp_path: Path):
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    assert parse_file(empty) == []
    repo = JobRepository(tmp_path / "e.db")
    preview = preview_import(empty, repo)
    assert preview.new_count == 0
    assert preview.skipped_dupe_count == 0
    repo.close()


def test_hash_prefixed_and_schemeless_youtube():
    text = "\n".join(
        [
            "# https://www.youtube.com/watch?v=jNQXAC9IVRw",
            "www.youtube.com/shorts/abcdefghijk",
            "youtu.be/jNQXAC9IVRw",
        ]
    )
    urls = [i.url for i in parse_lines(text)]
    assert urls == [WATCH, SHORTS, YOUTU]


def test_utf16_md_roundtrip(tmp_path: Path):
    path = tmp_path / "unicode.md"
    path.write_bytes(
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw\n" + SHORTS + "\n").encode("utf-16")
    )
    urls = [i.url for i in parse_file(path)]
    assert urls == [WATCH, SHORTS]


def test_preview_dedupe_existing_pending(tmp_path: Path):
    repo = JobRepository(tmp_path / "d.db")
    repo.enqueue(WATCH, title="already")
    preview = preview_import(FIX / "youtube_bulk.md", repo)
    assert preview.skipped_dupe_count >= 1
    assert all(i.url != WATCH for i in preview.items)
    assert preview.new_count > 0
    repo.close()


def test_preview_dialog_counts_new_urls(tmp_path: Path):
    """Same counts the Bulk import dialog shows (New URLs / Duplicates skipped)."""
    repo = JobRepository(tmp_path / "p.db")
    preview = preview_import(FIX / "youtube_bulk.md", repo)
    assert preview.new_count == 6
    assert preview.skipped_dupe_count == 0
    repo.close()


def test_import_enqueues_pending_does_not_arm(tmp_path: Path):
    repo = JobRepository(tmp_path / "idle.db")
    preview = preview_import(FIX / "youtube_bulk.md", repo)
    ids = confirm_add(preview, repo)
    assert len(ids) == 6
    assert all(repo.get(i).status == "pending" for i in ids)

    started: list[int] = []

    def handler(job: Job, r: JobRepository) -> None:
        started.append(job.id)

    worker = SequentialWorker(repo, download_handler=handler, poll_interval=0.02)
    worker.start(armed=False)
    time.sleep(0.15)
    assert started == []
    assert worker.is_armed is False
    assert all(repo.get(i).status == "pending" for i in ids)
    worker.stop(timeout=2)
    repo.close()
