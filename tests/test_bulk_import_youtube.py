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


def test_headings_set_category_and_porn_bucket(tmp_path: Path, monkeypatch):
    from frameforge.paths import download_dir_for_site

    root = tmp_path / "FrameForge"
    root.mkdir()
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(root))
    text = "\n".join(
        [
            "Squirting women.",
            "https://www.pornhub.com/view_video.php?viewkey=aaa",
            "1. https://www.pornhub.com/view_video.php?viewkey=bbb",
            "",
            "Another topic",
            "https://www.youtube.com/watch?v=ccccccccccc",
        ]
    )
    items = parse_lines(text)
    assert items[0].category == "Squirting women"
    assert items[1].category == "Squirting women"
    assert items[1].title is None
    assert items[2].category == "Another topic"
    repo = JobRepository(tmp_path / "cat.db")
    from frameforge.download.bulk_import import ImportPreview

    ids = confirm_add(ImportPreview(items=items), repo)
    assert len(ids) == 3
    ph = repo.get(ids[0])
    assert Path(ph.options()["download_output_dir"]) == download_dir_for_site(
        "pornhub.com", "Squirting women"
    )
    assert "porn" in Path(ph.options()["download_output_dir"]).parts
    yt = repo.get(ids[2])
    assert Path(yt.options()["download_output_dir"]) == download_dir_for_site(
        "youtube", "Another topic"
    )
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


def test_mixed_hosts_two_word_category_and_subject(tmp_path: Path, monkeypatch):
    from frameforge.download.bulk_import import ImportPreview
    from frameforge.paths import download_dir_for_site

    root = tmp_path / "FrameForge"
    root.mkdir()
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(root))
    items = parse_file(FIX / "mixed_import.md")
    by_url = {item.url: item for item in items}
    watch = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    desk = "https://x.com/example/status/1234567890"
    bbc = "https://www.bbc.com/news/city-council-vote"
    weather = "https://www.bbc.com/news/london-weather-update"
    adult = "https://www.pornhub.com/view_video.php?viewkey=aaa111"
    assert set(by_url) == {watch, desk, bbc, weather, adult}
    assert by_url[watch].category == "City council"
    assert by_url[desk].category == "City council"
    assert by_url[bbc].category == "City council"
    assert by_url[watch].title == "City council clip"
    assert by_url[desk].title == "City desk"
    assert by_url[bbc].title == "city council vote"
    assert "evening session" in (by_url[watch].note or "")
    assert "Notes from the packet." in (by_url[watch].note or "")
    assert by_url[weather].category == "Weather report"
    assert by_url[weather].title == "london weather update"
    assert by_url[adult].category == "Weather report"
    assert by_url[adult].title is None
    assert "https://" not in (by_url[adult].title or "")
    repo = JobRepository(tmp_path / "mix.db")
    ids = confirm_add(ImportPreview(items=items), repo)
    assert len(ids) == 5
    assert all(repo.get(i).status == "pending" for i in ids)
    yt = next(repo.get(i) for i in ids if repo.get(i).url == watch)
    assert Path(yt.options()["download_output_dir"]) == download_dir_for_site("youtube", "City council")
    assert yt.options()["import_note"].startswith("City council evening session")
    news = next(repo.get(i) for i in ids if repo.get(i).url == weather)
    assert Path(news.options()["download_output_dir"]) == download_dir_for_site(
        "bbc.com", "Weather report"
    )
    ph = next(repo.get(i) for i in ids if repo.get(i).url == adult)
    assert "porn" in Path(ph.options()["download_output_dir"]).parts
    assert ph.options()["download_category"] == "Weather report"
    repo.close()


def test_docx_rtf_and_doc_reach_the_same_parser(tmp_path: Path):
    import io
    import zipfile
    from xml.sax.saxutils import escape

    from frameforge.download.bulk_import import text_from_bytes

    body = "City council evening session\nhttps://www.youtube.com/watch?v=jNQXAC9IVRw\n"
    paragraph = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        + escape(body.splitlines()[0])
        + "</w:t></w:r></w:p><w:p><w:r><w:t>"
        + escape(body.splitlines()[1])
        + "</w:t></w:r></w:p></w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", paragraph)
    docx_items = parse_lines(text_from_bytes(buffer.getvalue(), ".docx"))
    assert docx_items[0].url == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert docx_items[0].category == "City council"

    rtf = r"{\rtf1\ansi City council evening session\par https://www.youtube.com/watch?v=jNQXAC9IVRw\par}"
    rtf_items = parse_lines(text_from_bytes(rtf.encode("latin-1"), ".rtf"))
    assert rtf_items[0].category == "City council"
    assert rtf_items[0].url.endswith("jNQXAC9IVRw")

    encoded = "City council evening session\nhttps://www.youtube.com/watch?v=jNQXAC9IVRw\n".encode("utf-16-le")
    doc_items = parse_lines(text_from_bytes(b"\xd0\xcf" + encoded, ".doc"))
    assert doc_items[0].category == "City council"
    assert doc_items[0].url.endswith("jNQXAC9IVRw")
