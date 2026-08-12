"""D2 — History tab population and basic actions."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.gui.app import FrameForgeApp


def test_hide_from_history_soft(tmp_path: Path):
    repo = JobRepository(tmp_path / "h.db")
    done = repo.enqueue("https://example.com/a", title="Done")
    failed = repo.enqueue("https://example.com/b", title="Fail")
    repo.update_status(done.id, "completed", progress=100)
    repo.update_status(failed.id, "failed", error="x")
    assert {j.id for j in repo.list_history()} == {done.id, failed.id}
    n = repo.hide_from_history([done.id])
    assert n == 1
    assert [j.id for j in repo.list_history()] == [failed.id]
    assert {j.id for j in repo.list_history(include_hidden=True)} == {done.id, failed.id}
    # Job still in SQLite / queue listing
    assert repo.get(done.id).status == "completed"
    repo.close()


def test_history_tab_lists_terminal_and_hide(tmp_path: Path):
    try:
        repo = JobRepository(tmp_path / "g.db")
        app = FrameForgeApp(repo=repo, start_worker=False)
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        pending = repo.enqueue("https://example.com/p", title="Pending")
        done = repo.enqueue("https://example.com/d", title="Finished", extractor="generic")
        failed = repo.enqueue("https://example.com/f", title="Broken")
        repo.update_status(done.id, "completed", progress=100)
        repo.update_status(failed.id, "failed", error="nope")
        app.refresh_queue()
        hist_ids = set(app.history_list._rows)
        assert done.id in hist_ids
        assert failed.id in hist_ids
        assert pending.id not in hist_ids
        assert pending.id in app.queue_list._rows

        app.history_list.set_selected({done.id})
        app.hide_history_selected()
        assert done.id not in app.history_list._rows
        assert done.id in app.queue_list._rows

        app.history_list.set_selected({failed.id})
        app.retry_history_selected()
        assert repo.get(failed.id).status == "pending"
    finally:
        app.destroy()
        repo.close()
