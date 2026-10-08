"""Every document listing is previewed and queued. No download starts."""

from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.download.bulk_import import confirm_add, parse_lines, preview_import, text_from_bytes
from frameforge.ui_flet.app import FrameForgeUi
from frameforge.queue.worker import SequentialWorker
from tests.flet_fakes import FakePage


def _docx(paragraphs: list[str], relationships: list[str]) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:body>"
        + "".join(f"<w:p>{p}</w:p>" for p in paragraphs)
        + "</w:body></w:document>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationships)
        + "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", rels)
    return buffer.getvalue()


def test_hyperlink_only_docx_previews_and_inserts_every_listing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(tmp_path / "home"))
    paragraphs: list[str] = []
    relationships: list[str] = []
    for i in range(500):
        rid = f"rId{i + 1}"
        url = f"https://example.com/listing/{i}"
        paragraphs.append(
            f'<w:hyperlink r:id="{rid}"><w:r><w:t>Listing {i}</w:t></w:r></w:hyperlink>'
        )
        relationships.append(
            f'<Relationship Id="{rid}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{url}" TargetMode="External"/>'
        )
    path = tmp_path / "listings.docx"
    path.write_bytes(_docx(paragraphs, relationships))
    repo = JobRepository(tmp_path / "q.db")
    preview = preview_import(path, repo)
    assert preview.listings_seen == 500
    assert preview.urls_found == 500
    assert preview.new_count == 500
    assert preview.skipped_dupe_count == 0
    commits = {"n": 0}

    def trace(sql: str) -> None:
        if sql.strip().upper() == "COMMIT":
            commits["n"] += 1

    repo.conn.set_trace_callback(trace)
    ids = confirm_add(preview, repo)
    assert len(ids) == 500
    assert preview.inserted_count == 500
    assert commits["n"] == 1
    assert repo.count_by_status("pending") == 500
    assert {repo.get(i).url for i in ids} == {f"https://example.com/listing/{n}" for n in range(500)}
    repo.close()


def test_wrapped_url_and_listing_path_are_one_job_each():
    text = "https://example.com/wrapped/part-\none\nhttps://example.com/search/tag/keep\n"
    items = parse_lines(text)
    urls = [item.url for item in items]
    assert urls == [
        "https://example.com/wrapped/part-one",
        "https://example.com/search/tag/keep",
    ]


def test_docx_wrapped_runs_and_search_hyperlink_are_kept():
    paragraphs = [
        "<w:r><w:t>https://example.com/split-</w:t></w:r><w:r><w:t>run</w:t></w:r>",
        '<w:hyperlink r:id="rId9"><w:r><w:t>Catalog</w:t></w:r></w:hyperlink>',
    ]
    rels = [
        '<Relationship Id="rId9" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.com/categories/feed/explore" TargetMode="External"/>'
    ]
    items = parse_lines(text_from_bytes(_docx(paragraphs, rels), ".docx"))
    assert [item.url for item in items] == [
        "https://example.com/split-run",
        "https://example.com/categories/feed/explore",
    ]


def test_doc_piece_table_split_is_one_url():
    url = "https://example.com/piece-table-video-name"
    left, right = url[:28], url[28:]
    blob = b"\xd0\xcf\x11\xe0" + left.encode("utf-16-le") + b"\x01\x00\x02" + right.encode("utf-16-le")
    items = parse_lines(text_from_bytes(blob, ".doc"))
    assert [item.url for item in items] == [url]


def test_archive_duplicate_is_skipped_and_not_downloaded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(tmp_path / "home"))
    repo = JobRepository(tmp_path / "a.db")
    kept = "https://example.com/already"
    fresh = "https://example.com/fresh"
    repo.add_archive(kept, title="done")
    path = tmp_path / "urls.txt"
    path.write_text(kept + "\n" + fresh + "\n", encoding="utf-8")
    preview = preview_import(path, repo)
    assert preview.listings_seen == 2
    assert preview.urls_found == 2
    assert preview.skipped_dupe_count == 1
    assert preview.new_count == 1
    ids = confirm_add(preview, repo)
    assert ids and repo.get(ids[0]).url == fresh
    assert repo.get(ids[0]).status == "pending"
    repo.close()


def test_import_dialog_reports_counts_and_inserts_off_the_ui_thread(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FRAMEFORGE_ROOT", str(tmp_path / "home"))
    from frameforge.download.bulk_import import confirm_add as real_confirm

    idents: dict[str, int] = {}

    def spy(preview, repo, **kwargs):
        idents["worker"] = threading.get_ident()
        return real_confirm(preview, repo, **kwargs)

    monkeypatch.setattr("frameforge.download.bulk_import.confirm_add", spy)
    repo = JobRepository(tmp_path / "ui.db")
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.page = FakePage()
    ui.exit_process_on_quit = True
    path = tmp_path / "two.txt"
    path.write_text("https://example.com/one\nhttps://example.com/two\n", encoding="utf-8")
    dlg = ui.show_import_preview(path)
    blob = " ".join(str(getattr(c, "value", c)) for c in dlg.content.controls)
    assert "Listings seen: 2" in blob
    assert "URLs found: 2" in blob
    assert "Duplicates skipped: 0" in blob
    assert "Rows to add: 2" in blob
    ui.confirm_bulk_import()
    ui._import_thread.join(timeout=10)
    assert idents["worker"] != threading.get_ident()
    assert ui.repo.count_by_status("pending") == 2
    assert ui.worker.is_armed is False
    ui.shutdown()
