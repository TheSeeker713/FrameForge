"""D1 — history queries and filters on on-disk SQLite."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository, TERMINAL_STATUSES


def test_list_history_filters_and_search(tmp_path: Path):
    repo = JobRepository(tmp_path / "hist.db")
    pending = repo.enqueue("https://example.com/pending", title="still going")
    done = repo.enqueue("https://youtube.com/a", title="Cat video", extractor="youtube")
    failed = repo.enqueue("https://vimeo.com/b", title="Fail clip", extractor="vimeo")
    cancelled = repo.enqueue("https://example.com/c", title="Nope")
    downloading = repo.enqueue("https://example.com/dl")
    repo.update_status(done.id, "completed", progress=100)
    repo.update_status(failed.id, "failed", error="boom")
    repo.update_status(cancelled.id, "cancelled")
    repo.update_status(downloading.id, "downloading")

    hist = repo.list_history()
    ids = {j.id for j in hist}
    assert ids == {done.id, failed.id, cancelled.id}
    assert pending.id not in ids
    assert downloading.id not in ids
    assert all(j.status in TERMINAL_STATUSES for j in hist)

    only_ok = repo.list_history(status="completed")
    assert [j.id for j in only_ok] == [done.id]
    only_fail = repo.list_history(status="failed")
    assert [j.id for j in only_fail] == [failed.id]
    only_cancel = repo.list_history(status="cancelled")
    assert [j.id for j in only_cancel] == [cancelled.id]

    by_title = repo.list_history(search="cat")
    assert [j.id for j in by_title] == [done.id]
    by_url = repo.list_history(search="vimeo.com")
    assert [j.id for j in by_url] == [failed.id]
    by_ext = repo.list_history(search="youtube")
    assert [j.id for j in by_ext] == [done.id]
    none = repo.list_history(search="zzzz-no-match")
    assert none == []

    # Active queue queries unchanged
    assert repo.count_by_status("pending") == 1
    assert repo.list_jobs("pending")[0].id == pending.id
    repo.close()
