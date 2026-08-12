"""Phase 1.6 — bulk TXT/MD importer (no network)."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import confirm_add, parse_file, preview_import

FIX = Path(__file__).parent / "fixtures"


def test_parse_txt_formats():
    items = parse_file(FIX / "bulk_urls.txt")
    urls = [i.url for i in items]
    assert "https://samplelib.com/lib/preview/mp4/sample-5s.mp4" in urls
    assert "https://samplelib.com/lib/preview/mp4/sample-10s.mp4" in urls
    assert "https://example.com/dup.mp4" in urls
    assert "https://example.com/md-clip.mp4" in urls
    # dedupe within file
    assert urls.count("https://example.com/dup.mp4") == 1
    titled = [i for i in items if i.url.endswith("sample-10s.mp4")][0]
    assert titled.title == "Title Example"


def test_parse_md_formats():
    items = parse_file(FIX / "bulk_urls.md")
    urls = {i.url for i in items}
    assert "https://example.com/bunny.mp4" in urls
    assert "https://example.com/plain.md.mp4" in urls
    assert "https://example.com/pipe.md.mp4" in urls
    bunny = [i for i in items if i.url.endswith("bunny.mp4")][0]
    assert bunny.title == "Bunny"


def test_preview_and_confirm_dedupe(tmp_path: Path):
    db = tmp_path / "bulk.db"
    repo = JobRepository(db)
    repo.enqueue("https://example.com/dup.mp4", title="already")
    preview = preview_import(FIX / "bulk_urls.txt", repo)
    assert preview.skipped_dupe_count >= 1
    assert all(i.url != "https://example.com/dup.mp4" for i in preview.items)
    ids = confirm_add(preview, repo)
    assert len(ids) == preview.new_count
    # Second confirm should add nothing new
    preview2 = preview_import(FIX / "bulk_urls.txt", repo)
    assert preview2.new_count == 0
    repo.close()
