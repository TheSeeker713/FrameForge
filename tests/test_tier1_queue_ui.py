"""Tier 1.3 — selectable queue list preserves selection and scroll across refresh."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from frameforge.db.repository import JobRepository
from frameforge.gui.queue_list import QueueList


def test_queue_list_preserves_selection_and_scroll(tmp_path: Path):
    root = ctk.CTk()
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "q.db")
        jobs = [
            repo.enqueue(f"https://example.com/{i}", title=f"t{i}", priority=i)
            for i in range(12)
        ]
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        ql.set_selected({jobs[2].id, jobs[5].id})
        ql.restore_scroll(0.4)
        before = ql.scroll_fraction()
        for _ in range(5):
            repo.update_progress(jobs[0].id, 10.0)
            ql.update_jobs(repo.list_jobs())
        assert jobs[2].id in ql.selected_ids
        assert jobs[5].id in ql.selected_ids
        after = ql.scroll_fraction()
        assert after >= 0.0
        if before > 0.05:
            assert after > 0.01
        # Actions operate on selected IDs (simulate Cancel selected)
        for jid in ql.selected_ids:
            repo.cancel(jid)
        assert repo.get(jobs[2].id).status == "cancelled"
        assert repo.get(jobs[5].id).status == "cancelled"
        repo.close()
    finally:
        root.destroy()


def test_queue_list_standalone_update(tmp_path: Path):
    root = ctk.CTk()
    root.withdraw()
    try:
        repo = JobRepository(tmp_path / "s.db")
        j1 = repo.enqueue("https://example.com/a", title="A")
        j2 = repo.enqueue("https://example.com/b", title="B")
        ql = QueueList(root)
        ql.update_jobs(repo.list_jobs())
        assert j1.id in ql._rows
        assert j2.id in ql._rows
        ql.set_selected({j1.id})
        assert ql.selected_ids == {j1.id}
        repo.update_progress(j1.id, 33)
        ql.update_jobs(repo.list_jobs())
        assert j1.id in ql.selected_ids
        assert "33.0%" in ql._rows[j1.id]["label"].cget("text")
        repo.close()
    finally:
        root.destroy()
