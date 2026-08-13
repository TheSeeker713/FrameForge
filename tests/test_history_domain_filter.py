"""Step 2.2 — history filters by status and domain."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository


def test_list_history_domain_filter(tmp_path: Path):
    repo = JobRepository(tmp_path / "d.db")
    yt = repo.enqueue("https://www.youtube.com/watch?v=jNQXAC9IVRw", title="zoo", extractor="youtube")
    vim = repo.enqueue("https://vimeo.com/123", title="vim", extractor="vimeo")
    repo.update_status(yt.id, "completed", progress=100)
    repo.update_status(vim.id, "failed", error="x")
    assert {j.id for j in repo.list_history()} == {yt.id, vim.id}
    only_yt = repo.list_history(domain="youtube")
    assert [j.id for j in only_yt] == [yt.id]
    only_vim = repo.list_history(domain="vimeo.com")
    assert [j.id for j in only_vim] == [vim.id]
    failed_yt = repo.list_history(status="failed", domain="youtube")
    assert failed_yt == []
    failed_vim = repo.list_history(status="failed", domain="vimeo")
    assert [j.id for j in failed_vim] == [vim.id]
    assert "youtube" in repo.history_domains()
    assert "vimeo" in repo.history_domains()
    repo.close()
